"""
GitHub Releases management via the `gh` CLI.

Handles creating releases (one per app/package), uploading APK assets,
and generating direct download URLs.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _run_gh(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a `gh` CLI command and return the result.

    The GH_TOKEN environment variable must be set for authentication.
    """
    cmd = ["gh"] + args
    logger.debug("Running: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,  # 5 min timeout for large uploads
    )

    if check and result.returncode != 0:
        logger.error("gh command failed (rc=%d): %s", result.returncode, result.stderr.strip())
        raise RuntimeError(f"gh CLI error: {result.stderr.strip()}")

    return result


def get_repo() -> str:
    """Get the current repository in owner/repo format.

    Uses GITHUB_REPOSITORY env var (set automatically in GitHub Actions),
    or falls back to `gh repo view`.
    """
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
        return repo

    result = _run_gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
    return result.stdout.strip()


def release_exists(tag: str) -> bool:
    """Check if a release with the given tag already exists."""
    result = _run_gh(["release", "view", tag, "--repo", get_repo()], check=False)
    return result.returncode == 0


def create_release(tag: str, title: str, notes: str = "") -> None:
    """Create a new GitHub release.

    Args:
        tag: Release tag (we use the package_name, e.g. 'com.miui.home').
        title: Human-readable release title.
        notes: Release description/body text.
    """
    if release_exists(tag):
        logger.info("Release '%s' already exists, skipping creation", tag)
        return

    logger.info("Creating release: %s (%s)", tag, title)
    _run_gh([
        "release", "create", tag,
        "--repo", get_repo(),
        "--title", title,
        "--notes", notes or f"Automatically synced APKs for {title}",
    ])


def upload_asset(tag: str, file_path: str | Path) -> str:
    """Upload an APK file as a release asset.

    If the asset already exists (same filename), it will be overwritten (--clobber).

    Args:
        tag: Release tag to upload to.
        file_path: Path to the APK file.

    Returns:
        Direct download URL for the uploaded asset.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info("Uploading %s to release '%s'", file_path.name, tag)
    _run_gh([
        "release", "upload", tag,
        str(file_path),
        "--repo", get_repo(),
        "--clobber",  # Overwrite if exists
    ])

    # Build the direct download URL
    repo = get_repo()
    download_url = f"https://github.com/{repo}/releases/download/{tag}/{file_path.name}"
    logger.info("Asset available at: %s", download_url)
    return download_url


def ensure_release_and_upload(
    package_name: str,
    app_name: str,
    apk_path: str | Path,
) -> str:
    """Create release if needed and upload the APK.

    Convenience function that combines create_release + upload_asset.

    Args:
        package_name: Package name used as the release tag.
        app_name: Human-readable app name for the release title.
        apk_path: Path to the APK file to upload.

    Returns:
        Direct download URL for the uploaded asset.
    """
    title = f"{app_name} ({package_name})"
    create_release(tag=package_name, title=title)
    return upload_asset(tag=package_name, file_path=apk_path)


def list_release_assets(tag: str) -> list[str]:
    """List all asset filenames in a release.

    Returns an empty list if the release doesn't exist.
    """
    if not release_exists(tag):
        return []

    result = _run_gh([
        "release", "view", tag,
        "--repo", get_repo(),
        "--json", "assets",
        "-q", ".assets[].name",
    ])
    return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
