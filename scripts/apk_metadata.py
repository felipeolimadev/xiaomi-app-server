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

    info = ApkInfo(
        package_name=package_name,
        version_name=version_name,
        version_code=version_code,
        min_sdk=min_sdk,
        target_sdk=target_sdk,
        app_name=app_name,
    )

    logger.info(
        "Extracted: %s v%s (code=%d)", info.package_name, info.version_name, info.version_code
    )
    return info


def _safe_int(value) -> int | None:
    """Convert a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
