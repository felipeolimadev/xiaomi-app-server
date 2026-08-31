"""
Main orchestrator for the Xiaomi App Server APK sync pipeline.

Runs exclusively via GitHub Actions.
Processes APKs streamingly (one by one) with a time-budget guard to prevent
workflow timeouts and ensure progress is never lost.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add scripts dir to path for local imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from apk_metadata import extract_apk_info
from catalog import load_catalog, save_catalog, version_exists, add_version, get_stats
from github_releases import ensure_release_and_upload, get_repo
from telegram_scraper import (
    CHANNELS,
    create_client,
    iter_channel_apk_messages,
    download_apk_file,
    get_channel_latest_id,
)

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT_DIR / "data" / "state.json"
CATALOG_PATH = ROOT_DIR / "data" / "apps.json"

# Safety time budget: exit cleanly after 10 minutes to allow commit/push
MAX_EXECUTION_TIME_SECONDS = 600

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def load_state() -> dict:
    """Load the channel state from disk."""
    if not STATE_PATH.exists():
        logger.warning("State file not found, starting fresh")
        return {"channels": {}}

    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load state: %s", exc)
        return {"channels": {}}


def save_state(state: dict) -> None:
    """Save the channel state to disk."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    logger.info("State saved to %s", STATE_PATH)


def get_channel_states(state: dict) -> dict[str, int]:
    """Extract last_message_id per channel from state."""
    channels = state.get("channels", {})
    return {
        name: info.get("last_message_id", 0)
        for name, info in channels.items()
    }


def update_channel_states(state: dict, updated_ids: dict[str, int]) -> None:
    """Update state with new last_message_id values."""
    now = datetime.now(timezone.utc).isoformat()
    channels = state.setdefault("channels", {})

    for channel_name, last_id in updated_ids.items():
        if channel_name not in channels:
            channels[channel_name] = {}
        channels[channel_name]["last_message_id"] = last_id
        channels[channel_name]["last_check"] = now


async def run() -> None:
    """Main async streaming pipeline."""
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("Xiaomi App Server — APK Sync Starting (Streaming Mode)")
    logger.info("=" * 60)

    # 1. Load state and catalog
    state = load_state()
    catalog = load_catalog(CATALOG_PATH)
    channel_states = get_channel_states(state)
    current_repo = get_repo()

    stats_before = get_stats(catalog)
    logger.info(
        "Catalog loaded: %d apps, %d total versions, %d regions",
        stats_before["total_apps"],
        stats_before["total_versions"],
        stats_before["total_regions"],
    )

    # 2. Connect to Telegram and stream APKs
    client = create_client()
    new_count = 0
    skipped_count = 0
    time_limit_reached = False

    async with client:
        logger.info("Connected to Telegram")

        for channel in CHANNELS:
            if time_limit_reached:
                break

            min_id = channel_states.get(channel, 0)
            logger.info("Processing channel: @%s (from min_id=%d)", channel, min_id)

            async for item in iter_channel_apk_messages(client, channel, min_id=min_id, limit=10):
                # Check time limit
                elapsed = time.time() - start_time
                if elapsed > MAX_EXECUTION_TIME_SECONDS:
                    logger.warning(
                        "Time budget reached (%.1fs / %ds). Stopping gracefully to save & commit.",
                        elapsed,
                        MAX_EXECUTION_TIME_SECONDS,
                    )
                    time_limit_reached = True
                    break

                logger.info(
                    "Processing APK from @%s [msg #%d]: %s (%.2f MB, region=%s)",
                    channel,
                    item.message.id,
                    item.file_name,
                    item.file_size / (1024 * 1024),
                    item.region,
                )

                apk_path: Path | None = None
                try:
                    # Download single APK
                    apk_path = await download_apk_file(item.message, item.file_name)

                    # Extract metadata from the APK binary
                    info = extract_apk_info(apk_path)

                    # Check deduplication (package + version + region)
                    if version_exists(catalog, info.package_name, info.version_code, item.region):
                        logger.info(
                            "SKIP: %s v%s (code=%d) [%s] already in catalog",
                            info.package_name,
                            info.version_name,
                            info.version_code,
                            item.region,
                        )
                        skipped_count += 1
                    else:
                        # Rename APK to standardized name (includes region)
                        std_filename = f"{info.package_name}_v{info.version_name}_{item.region}.apk"
                        std_path = apk_path.parent / std_filename
                        apk_path.rename(std_path)
                        apk_path = std_path

                        # Upload to GitHub Release
                        download_url = ensure_release_and_upload(
                            package_name=info.package_name,
                            app_name=info.app_name,
                            apk_path=std_path,
                        )

                        # Update catalog
                        add_version(
                            catalog=catalog,
                            package_name=info.package_name,
                            app_name=info.app_name,
                            version_name=info.version_name,
                            version_code=info.version_code,
                            file_name=std_filename,
                            file_size=item.file_size,
                            download_url=download_url,
                            min_sdk=info.min_sdk,
                            target_sdk=info.target_sdk,
                            source_channel=f"@{channel}",
                            region=item.region,
                            icon_path=info.icon_path,
                            repo=current_repo,
                        )
                        new_count += 1

                        # Save catalog to disk immediately
                        save_catalog(catalog, CATALOG_PATH)

                    # Update and save state with this message ID immediately
                    if item.message.id > channel_states.get(channel, 0):
                        channel_states[channel] = item.message.id
                        update_channel_states(state, {channel: item.message.id})
                        save_state(state)

                except Exception as exc:
                    logger.error(
                        "Failed to process msg #%d in @%s: %s",
                        item.message.id,
                        channel,
                        exc,
                        exc_info=True,
                    )
                finally:
                    # Clean up APK file from runner disk
                    if apk_path and apk_path.exists():
                        apk_path.unlink(missing_ok=True)

            # If min_id was 0 and we finished scanning without finding higher ID, update to channel tip
            if not time_limit_reached and channel_states.get(channel, 0) == 0:
                tip_id = await get_channel_latest_id(client, channel)
                if tip_id > 0:
                    channel_states[channel] = tip_id
                    update_channel_states(state, {channel: tip_id})
                    save_state(state)

    # Final save of state and catalog
    save_state(state)
    save_catalog(catalog, CATALOG_PATH)

    # Summary
    stats_after = get_stats(catalog)
    logger.info("=" * 60)
    logger.info("Sync run completed!")
    logger.info("  New APKs added: %d", new_count)
    logger.info("  Duplicates skipped: %d", skipped_count)
    logger.info(
        "  Catalog: %d apps, %d total versions, %d regions",
        stats_after["total_apps"],
        stats_after["total_versions"],
        stats_after["total_regions"],
    )
    if time_limit_reached:
        logger.info("  Note: Next scheduled run will continue where this run left off.")
    logger.info("=" * 60)


def main():
    """Entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
