"""
Set GitHub secrets for page_2 (Mama Roses → Sacred Sisters).
Usage: python set_github_secrets_page2.py --token "ghp_your_token_here"

Requires a GitHub PAT with 'repo' scope from:
https://github.com/settings/tokens/new?scopes=repo
"""
import argparse
import base64
import json
import sys
from pathlib import Path

import requests
from nacl import encoding, public

REPO = "zahraishandsome-svg/fb-fb-automation"
GITHUB_API = "https://api.github.com"

SECRETS = {
    "PAGE_2_SOURCE_CREDENTIALS": "credentials/page_2_source_credentials.json",
    "PAGE_2_SOURCE_TOKEN":        "tokens/page_2_source_token.json",
    "PAGE_2_DEST_CREDENTIALS":   "credentials/page_2_dest_credentials.json",
    "PAGE_2_DEST_TOKEN":         "tokens/page_2_dest_token.json",
}


def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    """Encrypt secret value with the repo's public key (libsodium sealed box)."""
    public_key_bytes = base64.b64decode(public_key_b64)
    sealed_box = public.SealedBox(public.PublicKey(public_key_bytes))
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def get_repo_public_key(session: requests.Session) -> tuple[str, str]:
    """Returns (key_id, key_b64)."""
    r = session.get(f"{GITHUB_API}/repos/{REPO}/actions/secrets/public-key")
    r.raise_for_status()
    data = r.json()
    return data["key_id"], data["key"]


def set_secret(session: requests.Session, key_id: str, key_b64: str,
               name: str, value: str) -> None:
    encrypted = encrypt_secret(key_b64, value)
    r = session.put(
        f"{GITHUB_API}/repos/{REPO}/actions/secrets/{name}",
        json={"encrypted_value": encrypted, "key_id": key_id},
    )
    if r.status_code in (201, 204):
        print(f"  OK: {name}")
    else:
        print(f"  FAIL: {name}: {r.status_code} {r.text}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True, help="GitHub PAT with repo scope")
    args = parser.parse_args()

    root = Path(__file__).parent
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {args.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    print(f"Getting repo public key for {REPO}...")
    key_id, key_b64 = get_repo_public_key(session)
    print(f"Key ID: {key_id}")

    print("\nSetting secrets:")
    for secret_name, file_path in SECRETS.items():
        file_content = (root / file_path).read_text(encoding="utf-8")
        # Base64-encode so the workflow can do: echo "$SECRET" | base64 -d > file.json
        b64_value = base64.b64encode(file_content.encode("utf-8")).decode("utf-8")
        set_secret(session, key_id, key_b64, secret_name, b64_value)

    print("\nAll 4 page_2 secrets set successfully.")
    print("Next: commit and push, then page_2 will go live on the next cron run.")


if __name__ == "__main__":
    main()
