# Xiaomi App Server

Automated Xiaomi/HyperOS system app APK repository. Monitors Telegram channels for new APK releases and publishes them via GitHub Releases with a machine-readable JSON catalog.

## How it Works

```
Telegram Channels ──► GitHub Actions (hourly) ──► GitHub Releases
       │                       │                        │
       │                       ▼                        │
       │                 Extract metadata               │
       │                 (androguard)                    │
       │                       │                        │
       │                       ▼                        │
       │                Deduplication check              │
       │               (apps.json catalog)              │
       │                       │                        │
       │                       ▼                        ▼
       └──────────────► Download APK ──────────► Upload to Release
                                                        │
                                                        ▼
                                                 Update apps.json
                                                 (commit & push)
```

### Monitored Channels

| Channel | Focus |
|---------|-------|
| [@hyperossystemapps](https://t.me/hyperossystemapps) | HyperOS system apps |
| [@MiuiSystemUpdater](https://t.me/MiuiSystemUpdater) | MIUI/HyperOS system updates |
| [@HyperOsUpdates](https://t.me/HyperOsUpdates) | HyperOS general updates |

## Setup

### 1. Get Telegram API Credentials

1. Go to [my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Go to **API Development Tools**
4. Create an app and note the **API ID** and **API Hash**

### 2. Generate a StringSession

Run the session generator locally (requires Python 3.10+):

```bash
pip install telethon
python scripts/generate_session.py
```

This will prompt for your phone number and verification code, then output a `StringSession` string.

### 3. Configure GitHub Secrets

In your GitHub repository, go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|--------|-------------|
| `TELEGRAM_API_ID` | Your numeric API ID |
| `TELEGRAM_API_HASH` | Your alphanumeric API hash |
| `TELEGRAM_STRING_SESSION` | The StringSession from step 2 |

> `GITHUB_TOKEN` is provided automatically by GitHub Actions.

### 4. Enable the Workflow

The workflow runs automatically every hour. You can also trigger it manually from the **Actions** tab → **Sync Xiaomi APKs** → **Run workflow**.

## APK Catalog (`data/apps.json`)

The catalog is a JSON file updated on every sync. It contains all discovered apps and their versions with direct download links.

### Schema

```json
{
  "last_updated": "2026-08-28T15:00:00Z",
  "apps": {
    "com.miui.home": {
      "name": "Mi Launcher",
      "package_name": "com.miui.home",
      "latest_version": "4.39.14.7554",
      "latest_version_code": 414739014,
      "updated_at": "2026-08-28T14:30:00Z",
      "versions": [
        {
          "version_name": "4.39.14.7554",
          "version_code": 414739014,
          "file_name": "com.miui.home_v4.39.14.7554.apk",
          "file_size": 52428800,
          "download_url": "https://github.com/.../releases/download/com.miui.home/com.miui.home_v4.39.14.7554.apk",
          "min_sdk": 30,
          "target_sdk": 34,
          "source_channel": "@hyperossystemapps",
          "discovered_at": "2026-08-28T14:30:00Z"
        }
      ]
    }
  }
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `package_name` | Android package identifier (e.g., `com.miui.home`) |
| `latest_version` | Most recent version name |
| `latest_version_code` | Numeric version code (used for comparison) |
| `download_url` | Direct link to download the APK from GitHub Releases |
| `source_channel` | Telegram channel where the APK was found |

## Deduplication

APKs are deduplicated using two layers:

1. **Telegram layer** — `state.json` tracks the last processed `message_id` per channel. Only new messages are fetched on each run.
2. **APK layer** — After downloading, metadata is extracted from the APK binary. The key `(package_name, version_code)` is checked against `apps.json`. Duplicates (same APK posted in multiple channels) are skipped.

## GitHub Releases Structure

Each app gets its own Release, tagged with the package name:

```
Release: com.miui.home
  └── com.miui.home_v4.39.14.7554.apk
  └── com.miui.home_v4.38.12.7321.apk

Release: com.miui.gallery
  └── com.miui.gallery_v3.5.7.8.apk
```

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export TELEGRAM_API_ID="your_id"
export TELEGRAM_API_HASH="your_hash"
export TELEGRAM_STRING_SESSION="your_session"

# Run (dry-run mode when not in GitHub Actions)
python scripts/main.py
```

In dry-run mode (local), APKs are downloaded and metadata is extracted, but uploads to GitHub Releases are simulated with placeholder URLs.

## Project Structure

```
├── .github/workflows/
│   └── sync-apks.yml          # Hourly cron workflow
├── scripts/
│   ├── generate_session.py    # One-time StringSession generator
│   ├── apk_metadata.py       # APK metadata extraction (androguard)
│   ├── telegram_scraper.py   # Telegram channel scraper (telethon)
│   ├── github_releases.py    # GitHub Releases management (gh CLI)
│   ├── catalog.py            # apps.json catalog manager
│   └── main.py               # Main orchestrator
├── data/
│   ├── apps.json              # APK catalog (auto-updated)
│   └── state.json             # Scraper state (auto-updated)
├── requirements.txt
└── README.md
```

## License

MIT
