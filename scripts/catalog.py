"""
Manage the apps.json catalog file.

Handles loading, saving, deduplication checks, and adding new APK
version entries to the catalog. Supports region-based separation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path to the catalog file relative to the repo root
CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "apps.json"


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    """Load the apps catalog from disk.

    Returns an empty catalog structure if the file doesn't exist or is invalid.
    """
    catalog_path = path or CATALOG_PATH

    if not catalog_path.exists():
        logger.warning("Catalog not found at %s, starting fresh", catalog_path)
        return _empty_catalog()

    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Validate minimal structure
        if "apps" not in data:
            logger.warning("Catalog missing 'apps' key, starting fresh")
            return _empty_catalog()
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load catalog: %s", exc)
        return _empty_catalog()


def save_catalog(catalog: dict[str, Any], path: Path | None = None) -> None:
    """Save the apps catalog to disk."""
    catalog_path = path or CATALOG_PATH

    catalog["last_updated"] = datetime.now(timezone.utc).isoformat()

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    logger.info("Catalog saved to %s", catalog_path)


def version_exists(
    catalog: dict[str, Any],
    package_name: str,
    version_code: int,
    region: str,
) -> bool:
    """Check if a specific version+region of an app already exists in the catalog.

    Deduplication key: (package_name, version_code, region)
    The same version can exist for different regions (e.g. China vs Global).
    """
    app = catalog.get("apps", {}).get(package_name)
    if not app:
        return False

    for version in app.get("versions", []):
        if (
            version.get("version_code") == version_code
            and version.get("region") == region
        ):
            return True

    return False


def add_version(
    catalog: dict[str, Any],
    package_name: str,
    app_name: str,
    version_name: str,
    version_code: int,
    file_name: str,
    file_size: int,
    download_url: str,
    min_sdk: int | None,
    target_sdk: int | None,
    source_channel: str,
    region: str,
    icon_path: str | None = None,
    repo: str | None = None,
) -> None:
    """Add a new version entry to the catalog.

    Creates the app entry if it doesn't exist. Updates latest_version
    fields if this version has a higher version_code.
    """
    apps = catalog.setdefault("apps", {})
    now = datetime.now(timezone.utc).isoformat()

    version_entry = {
        "version_name": version_name,
        "version_code": version_code,
        "region": region,
        "file_name": file_name,
        "file_size": file_size,
        "download_url": download_url,
        "min_sdk": min_sdk,
        "target_sdk": target_sdk,
        "source_channel": source_channel,
        "discovered_at": now,
    }

    icon_url = f"https://raw.githubusercontent.com/{repo}/main/{icon_path}" if (icon_path and repo) else None

    if package_name not in apps:
        # New app — create full entry
        apps[package_name] = {
            "name": app_name,
            "package_name": package_name,
            "icon": icon_path,
            "icon_url": icon_url,
            "latest_version": version_name,
            "latest_version_code": version_code,
            "updated_at": now,
            "versions": [version_entry],
        }
        logger.info(
            "New app added: %s (%s) v%s [%s]",
            app_name, package_name, version_name, region,
        )
    else:
        # Existing app — append version
        app = apps[package_name]
        app["versions"].append(version_entry)

        # Update icon if missing
        if not app.get("icon") and icon_path:
            app["icon"] = icon_path
            app["icon_url"] = icon_url

        # Update latest if this version is newer
        if version_code > (app.get("latest_version_code") or 0):
            app["latest_version"] = version_name
            app["latest_version_code"] = version_code
            app["updated_at"] = now

        # Keep app name updated (some channels provide better names)
        if app_name and app_name != package_name:
            app["name"] = app_name

        logger.info(
            "New version for %s: v%s (code=%d) [%s]",
            package_name, version_name, version_code, region,
        )


def get_stats(catalog: dict[str, Any]) -> dict[str, int]:
    """Get summary statistics from the catalog."""
    apps = catalog.get("apps", {})
    total_versions = sum(len(app.get("versions", [])) for app in apps.values())

    # Count unique regions
    regions = set()
    for app in apps.values():
        for v in app.get("versions", []):
            regions.add(v.get("region", "unknown"))

    return {
        "total_apps": len(apps),
        "total_versions": total_versions,
        "total_regions": len(regions),
    }


def _empty_catalog() -> dict[str, Any]:
    """Return an empty catalog structure."""
    return {
        "last_updated": None,
        "apps": {},
    }
