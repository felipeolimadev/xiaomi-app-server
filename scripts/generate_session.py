"""
Generate a Telethon StringSession for headless/CI authentication.

Run this script ONCE on your local machine. It will ask for:
  1. Your Telegram API ID and API Hash (from https://my.telegram.org)
  2. Your phone number
  3. The verification code sent to your Telegram
  4. Your 2FA password (if enabled)

The output is a StringSession string to store as a GitHub Secret.
"""

from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def main():
    print("=" * 60)
    print("  Telethon StringSession Generator")
    print("  Obtain API credentials at: https://my.telegram.org")
    print("=" * 60)
    print()

    api_id = int(input("Enter your API ID: ").strip())
    api_hash = input("Enter your API Hash: ").strip()

    print("\nConnecting to Telegram...")
    print("You will be prompted for your phone number and verification code.\n")

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_string = client.session.save()

        print("\n" + "=" * 60)
        print("  SUCCESS! Your StringSession is below.")
        print("  Store it as TELEGRAM_STRING_SESSION in GitHub Secrets.")
        print("=" * 60)
        print()
        print(session_string)
        print()
        print("=" * 60)
        print("  WARNING: This session grants full access to your")
        print("  Telegram account. Keep it secret!")
        print("  If compromised, revoke at:")
        print("  Telegram Settings > Devices > Active Sessions")
        print("=" * 60)


if __name__ == "__main__":
    main()
