"""
Main orchestrator for the Xiaomi App Server APK sync pipeline.

Runs exclusively via GitHub Actions. Flow:
  1. Load state.json (last processed message IDs) and apps.json (catalog)
  2. Connect to Telegram via StringSession
  3. Scrape each channel for new APK messages
  4. For each new APK:
     a. Extract metadata (package_name, version) via androguard
     b. Detect region from caption/filename
     c. Check deduplication against apps.json (package + version + region)
     d. Upload to GitHub Release (one release per app)
     e. Update apps.json with new version entry
  5. Save updated state.json and apps.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add scripts dir to path for local imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from apk_metadata import extract_apk_info
from catalog import load_catalog, save_catalog, version_exists, add_version, get_stats
from github_releases import ensure_release_and_upload
from telegram_scraper import create_client, scrape_all_channels

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT_DIR / "data" / "state.json"
CATALOG_PATH = ROOT_DIR / "data" / "apps.json"
DOWNLOADS_DIR = ROOT_DIR / "downloads"

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
    """Main async pipeline."""
    logger.info("=" * 60)
    logger.info("Xiaomi App Server — APK Sync Starting")
    logger.info("=" * 60)

    # 1. Load state and catalog
    state = load_state()
    catalog = load_catalog(CATALOG_PATH)
    channel_states = get_channel_states(state)

    stats_before = get_stats(catalog)
    logger.info(
        "Catalog loaded: %d apps, %d total versions, %d regions",
        stats_before["total_apps"],
        stats_before["total_versions"],
        stats_before["total_regions"],
    )

    # 2. Connect to Telegram and scrape channels
    client = create_client()

    async with client:
        logger.info("Connected to Telegram")

        downloaded_apks, updated_ids = await scrape_all_channels(
            client, channel_states
        )

    if not downloaded_apks:
        logger.info("No new APKs found. Updating state and exiting.")
        update_channel_states(state, updated_ids)
        save_state(state)
        return

    logger.info("Processing %d downloaded APKs...", len(downloaded_apks))

    # 3. Process each downloaded APK
    new_count = 0
    skipped_count = 0

    for apk in downloaded_apks:
        try:
            # 3a. Extract metadata from the APK binary
            info = extract_apk_info(apk.file_path)

            # 3b. Check deduplication (package + version + region)
            if version_exists(catalog, info.package_name, info.version_code, apk.region):
                logger.info(
                    "SKIP: %s v%s (code=%d) [%s] already in catalog",
                    info.package_name,
                    info.version_name,
                    info.version_code,
                    apk.region,
                )
                skipped_count += 1
                # Clean up downloaded file
                apk.file_path.unlink(missing_ok=True)
                continue

            # 3c. Rename APK to standardized name (includes region)
            std_filename = f"{info.package_name}_v{info.version_name}_{apk.region}.apk"
            std_path = apk.file_path.parent / std_filename
            apk.file_path.rename(std_path)

            # 3d. Upload to GitHub Release
            download_url = ensure_release_and_upload(
                package_name=info.package_name,
                app_name=info.app_name,
                apk_path=std_path,
            )

            # 3e. Update catalog
            add_version(
                catalog=catalog,
                package_name=info.package_name,
                app_name=info.app_name,
                version_name=info.version_name,
                version_code=info.version_code,
                file_name=std_filename,
                file_size=apk.file_size,
                download_url=download_url,
                min_sdk=info.min_sdk,
                target_sdk=info.target_sdk,
                source_channel=f"@{apk.channel}",
                region=apk.region,
            )
            new_count += 1

            # Save immediately to disk on each processed APK
            save_catalog(catalog, CATALOG_PATH)

            # Clean up downloaded file after upload
            std_path.unlink(missing_ok=True)

        except Exception as exc:
            logger.error(
                "Failed to process %s: %s",
                apk.file_name,
                exc,
                exc_info=True,
            )
            # Clean up on failure
            apk.file_path.unlink(missing_ok=True)

    # 4. Save final state and catalog
    update_channel_states(state, updated_ids)
    save_state(state)
    save_catalog(catalog, CATALOG_PATH)

    # 5. Summary
    stats_after = get_stats(catalog)
    logger.info("=" * 60)
    logger.info("Sync complete!")
    logger.info("  New APKs added: %d", new_count)
    logger.info("  Duplicates skipped: %d", skipped_count)
    logger.info(
        "  Catalog: %d apps, %d total versions, %d regions",
        stats_after["total_apps"],
        stats_after["total_versions"],
        stats_after["total_regions"],
    )
    logger.info("=" * 60)


def main():
    """Entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
