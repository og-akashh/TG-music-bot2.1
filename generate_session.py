"""
generate_session.py — Interactive helper to generate a Pyrogram STRING SESSION.

Run this script ONCE on your local machine (not on the server) to obtain
the SESSION_STRING value for your .env file.

Usage:
    python generate_session.py

You will be prompted for:
  1. Your Telegram phone number (e.g. +1234567890)
  2. The OTP Telegram sends to your account
  3. Your 2FA password (if enabled)

The resulting string is printed at the end.
NEVER share this string with anyone — it grants full access to your account.
"""

import asyncio

from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded


async def main():
    print("=" * 60)
    print("  Pyrogram String Session Generator")
    print("=" * 60)
    print()

    api_id   = int(input("Enter your API_ID   : ").strip())
    api_hash = input("Enter your API_HASH  : ").strip()

    print()
    print("A Telegram login code will be sent to your account.")
    print()

    async with Client(
        name="session_generator",
        api_id=api_id,
        api_hash=api_hash,
        in_memory=True,
    ) as app:
        print()
        print("✅ Authorised successfully!")
        session_string = await app.export_session_string()

    print()
    print("=" * 60)
    print("  Your SESSION_STRING (add to .env):")
    print("=" * 60)
    print()
    print(session_string)
    print()
    print("Keep this string SECRET. Do not share or commit it.")


if __name__ == "__main__":
    asyncio.run(main())
