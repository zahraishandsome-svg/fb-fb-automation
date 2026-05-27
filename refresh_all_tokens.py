#!/usr/bin/env python3
"""
Refresh Facebook Page tokens for ALL pages in channels.yaml at once.

Usage:
  python refresh_all_tokens.py --type dest --token "EAAxxxxx..."
  python refresh_all_tokens.py --type source --token "EAAxxxxx..."

  --type dest   : refreshes all DESTINATION page tokens (pages you post to)
  --type source : refreshes all SOURCE page tokens (pages you read videos from)

Steps:
  1. Takes a short-lived user token from Graph API Explorer
  2. Exchanges it for a long-lived user token (~60 days)
  3. Calls /me/accounts to get tokens for ALL managed pages in one shot
  4. Matches pages by page_id from credentials files
  5. Saves all token files at once

Get token at: https://developers.facebook.com/tools/explorer/
Dest permissions:  pages_manage_posts, pages_show_list, publish_video
Source permissions: pages_read_engagement, pages_show_list
"""

import argparse
import sys
import requests
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config import load_config, load_credentials, save_token
from src.facebook_poster import get_long_lived_token

GRAPH_URL = "https://graph.facebook.com/v19.0"


def get_all_page_tokens(user_token: str) -> dict:
    """Call /me/accounts to get tokens for all pages managed by this user."""
    all_pages = {}
    url = f"{GRAPH_URL}/me/accounts"
    params = {"access_token": user_token, "limit": 100}

    while url:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for page in data.get("data", []):
            all_pages[page["id"]] = page["access_token"]
        next_url = data.get("paging", {}).get("next")
        url = next_url if next_url else None
        params = {}

    return all_pages


def main():
    parser = argparse.ArgumentParser(description="Refresh ALL Facebook page tokens at once")
    parser.add_argument("--type", required=True, choices=["dest", "source"],
                        help="Which tokens to refresh: 'dest' (pages you post to) or 'source' (pages you read from)")
    parser.add_argument("--token", required=True,
                        help="Short-lived user token from developers.facebook.com/tools/explorer/")
    args = parser.parse_args()

    config = load_config()
    channels = [ch for ch in config["channels"] if ch.get("enabled", True)]

    if not channels:
        print("No enabled channels found in channels.yaml")
        sys.exit(1)

    # Pick credentials and token file based on type
    if args.type == "dest":
        creds_key = "dest_credentials_file"
        token_key = "dest_token_file"
        label = "destination"
        name_key = "dest_page_name"
    else:
        creds_key = "source_credentials_file"
        token_key = "source_token_file"
        label = "source"
        name_key = "source_page_name"

    # Use first channel's app credentials for token exchange
    first_creds = load_credentials(channels[0][creds_key])
    app_id = first_creds["app_id"]
    app_secret = first_creds["app_secret"]

    print(f"Refreshing all {label} page tokens (app: {app_id})...")
    print(f"Exchanging short-lived token for long-lived user token...")
    token_resp = get_long_lived_token(args.token, app_id, app_secret)
    long_lived_token = token_resp["access_token"]
    expires_at = (date.today() + timedelta(days=58)).isoformat()
    print(f"Got long-lived token. Expires ~{expires_at}\n")

    print("Fetching all page tokens via /me/accounts...")
    all_page_tokens = get_all_page_tokens(long_lived_token)
    print(f"Found {len(all_page_tokens)} page(s) under this account\n")

    updated = 0
    skipped = 0
    for channel in channels:
        creds = load_credentials(channel[creds_key])
        page_id = creds["page_id"]
        page_name = channel.get(name_key, channel["id"])

        if page_id not in all_page_tokens:
            print(f"⚠️  {channel['id']} ({page_name}) — page {page_id} not found. "
                  f"Make sure this page is connected to the app in Graph Explorer.")
            skipped += 1
            continue

        token_data = {
            "page_access_token": all_page_tokens[page_id],
            "user_access_token": long_lived_token,
            "expires_at": expires_at,
        }
        save_token(channel[token_key], token_data)
        print(f"✓  {channel['id']} ({page_name}) → saved to {channel[token_key]}")
        updated += 1

    print(f"\n{'='*50}")
    print(f"Done. {updated} refreshed, {skipped} skipped.")
    if updated > 0:
        print(f"Test with: python run.py --slot 1 --dry-run")


if __name__ == "__main__":
    main()
