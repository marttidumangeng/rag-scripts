#!/usr/bin/env python
"""
Find conversion action ID by name in Google Ads account.
"""

import os
import sys
from pathlib import Path

import requests

TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def load_env_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def mint_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    payload = {
        "client_id": client_id,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    if client_secret:
        payload["client_secret"] = client_secret

    response = requests.post(TOKEN_ENDPOINT, data=payload, timeout=60)
    if not response.ok:
        raise RuntimeError(f"OAuth token endpoint failed ({response.status_code}): {response.text}")
    body = response.json()
    token = (body.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("OAuth token endpoint did not return access_token")
    return token


def main():
    # Load env
    env_file = Path("scripts/.env")
    load_env_file(env_file)

    customer_id = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "").strip()
    developer_token = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip()
    client_id = os.getenv("GOOGLE_ADS_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_ADS_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("GOOGLE_ADS_REFRESH_TOKEN", "").strip()

    if not all([customer_id, developer_token, client_id, refresh_token]):
        print("ERROR: Missing required env vars (GOOGLE_ADS_CUSTOMER_ID, GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_REFRESH_TOKEN)")
        return 1

    # Mint token
    print("Minting access token...")
    try:
        access_token = mint_access_token(client_id, client_secret, refresh_token)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    # Query conversion actions
    endpoint = f"https://googleads.googleapis.com/v24/customers/{customer_id}/conversionActions"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "developer-token": developer_token,
    }

    print(f"Fetching conversion actions for customer {customer_id}...")
    response = requests.get(endpoint, headers=headers, timeout=60)
    if not response.ok:
        print(f"ERROR: {response.status_code} - {response.text}")
        return 1

    data = response.json()
    resources = data.get("results", []) or []

    if not resources:
        print("No conversion actions found.")
        return 0

    print(f"\nFound {len(resources)} conversion actions:\n")
    for resource in resources:
        name_parts = resource.get("resourceName", "").split("/")
        action_id = name_parts[-1] if name_parts else "?"
        display_name = resource.get("name", "?")
        print(f"  ID: {action_id:20} Name: {display_name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
