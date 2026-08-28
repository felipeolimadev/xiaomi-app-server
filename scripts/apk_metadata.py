"""
Extract metadata from APK files using androguard.

Provides reliable package name, version, and SDK info directly from
the APK binary (AndroidManifest.xml), instead of parsing Telegram captions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from pathlib import Path

from androguard.core.apk import APK

logger = logging.getLogger(__name__)


@dataclass
class ApkInfo:
    """Metadata extracted from an APK file."""

    package_name: str
    version_name: str
    version_code: int
    min_sdk: int | None
    target_sdk: int | None
    app_name: str
    icon_path: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def extract_apk_info(apk_path: str | Path) -> ApkInfo:
    """Extract metadata from an APK file.

    Args:
        apk_path: Path to the .apk file.

    Returns:
        ApkInfo with package name, version, and SDK details.

    Raises:
        ValueError: If the APK cannot be parsed or is missing critical fields.
    """
    apk_path = Path(apk_path)
    if not apk_path.exists():
        raise FileNotFoundError(f"APK not found: {apk_path}")

    logger.info("Extracting metadata from: %s", apk_path.name)

    try:
        apk = APK(str(apk_path))
    except Exception as exc:
        raise ValueError(f"Failed to parse APK '{apk_path.name}': {exc}") from exc

    package_name = apk.get_package()
    version_name = apk.get_androidversion_name()
    version_code_raw = apk.get_androidversion_code()

    if not package_name:
        raise ValueError(f"APK '{apk_path.name}' has no package name")
    if not version_name:
        raise ValueError(f"APK '{apk_path.name}' has no version name")

    # version_code can be None in rare cases; default to 0
    try:
        version_code = int(version_code_raw) if version_code_raw else 0
    except (ValueError, TypeError):
        version_code = 0
        logger.warning(
            "Could not parse version_code '%s' for %s, defaulting to 0",
            version_code_raw,
            package_name,
        )

    # SDK versions
    min_sdk = _safe_int(apk.get_min_sdk_version())
    target_sdk = _safe_int(apk.get_target_sdk_version())

    # App display name
    app_name = apk.get_app_name() or package_name

    # App icon extraction (check if already exists in repository)
    icons_dir = Path(__file__).resolve().parent.parent / "icons"
    icon_rel_path = extract_or_get_icon(apk, package_name, icons_dir)

    info = ApkInfo(
        package_name=package_name,
        version_name=version_name,
        version_code=version_code,
        min_sdk=min_sdk,
        target_sdk=target_sdk,
        app_name=app_name,
        icon_path=icon_rel_path,
    )

    logger.info(
        "Extracted: %s v%s (code=%d, icon=%s)",
        info.package_name,
        info.version_name,
        info.version_code,
        info.icon_path,
    )
    return info


def extract_or_get_icon(apk: APK, package_name: str, icons_dir: Path) -> str | None:
    """Extract app icon from APK to icons_dir/package_name.png if not already present.

    Returns relative path to the icon (e.g. 'icons/com.miui.home.png') or None.
    """
    icons_dir.mkdir(parents=True, exist_ok=True)

    # 1. Check if icon already exists in repo
    for ext in [".png", ".webp", ".jpg"]:
        existing = icons_dir / f"{package_name}{ext}"
        if existing.exists() and existing.stat().st_size > 0:
            logger.info("Icon already exists for %s: %s", package_name, existing.name)
            return f"icons/{existing.name}"

    # 2. Extract from APK binary if not present
    try:
        icon_path = apk.get_app_icon()
        data = None
        ext = ".png"

        if icon_path and (icon_path.endswith(".png") or icon_path.endswith(".webp") or icon_path.endswith(".jpg")):
            data = apk.get_file(icon_path)
            ext = Path(icon_path).suffix or ".png"
        else:
            # Fallback: search for highest resolution raster launcher icon
            candidates = []
            for fname in apk.get_files():
                fname_lower = fname.lower()
                if (fname_lower.endswith(".png") or fname_lower.endswith(".webp")) and (
                    "ic_launcher" in fname_lower or "icon" in fname_lower or "logo" in fname_lower
                ):
                    score = 0
                    if "xxxhdpi" in fname_lower:
                        score = 5
                    elif "xxhdpi" in fname_lower:
                        score = 4
                    elif "xhdpi" in fname_lower:
                        score = 3
                    elif "hdpi" in fname_lower:
                        score = 2
                    elif "mdpi" in fname_lower:
                        score = 1
                    candidates.append((score, fname))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                best_file = candidates[0][1]
                data = apk.get_file(best_file)
                ext = Path(best_file).suffix or ".png"

        if data:
            dest_file = icons_dir / f"{package_name}{ext}"
            dest_file.write_bytes(data)
            logger.info("Saved icon for %s: %s (%d bytes)", package_name, dest_file.name, len(data))
            return f"icons/{dest_file.name}"

    except Exception as exc:
        logger.warning("Could not extract icon for %s: %s", package_name, exc)

    return None


def _safe_int(value) -> int | None:
    """Convert a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
