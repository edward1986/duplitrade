import os
import sys
import json
import requests
from datetime import datetime, timezone

SIGNIN_URL = "https://fa.new.duplitrade.com/api/auth/signin"
OPEN_POSITIONS_URL = "https://fa.new.duplitrade.com/api/user/get_provider_open_positions"

def require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        print(f"Missing env var: {name}", file=sys.stderr)
        sys.exit(2)
    return v

def signin_and_get_token(email: str, password: str) -> str:
    r = requests.post(
        SIGNIN_URL,
        json={"email": email, "password": password},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if not r.ok:
        print("Signin failed:", r.status_code, r.text, file=sys.stderr)
        sys.exit(1)

    try:
        data = r.json()
    except ValueError:
        print("Signin did not return JSON:", r.text, file=sys.stderr)
        sys.exit(1)

    token = (
        data.get("token")
        or data.get("tokn")
        or data.get("access_token")
        or data.get("accessToken")
        or (data.get("data") or {}).get("token")
        or (data.get("data") or {}).get("tokn")
    )

    if not token:
        print("Token not found in signin response keys:", list(data.keys()), file=sys.stderr)
        sys.exit(1)

    return token

def fetch_open_positions(provider_id: str, token: str):
    r = requests.get(
        OPEN_POSITIONS_URL,
        params={"provider_id": provider_id},
        headers={
            "Accept": "application/json",
            "token": token,  # header name exactly: token
        },
        timeout=30,
    )
    if not r.ok:
        print("Open positions failed:", r.status_code, r.text, file=sys.stderr)
        sys.exit(1)

    try:
        return r.json()
    except ValueError:
        # If API returns non-JSON, still save it as text payload
        return {"raw": r.text}

def main():
    email = require_env("FA_EMAIL")
    password = require_env("FA_PASSWORD")
    provider_id = os.getenv("PROVIDER_ID", "931")

    token = signin_and_get_token(email, password)
    positions = fetch_open_positions(provider_id, token)

    # Store in repo under /open_positions/<provider_id>.json
    out_dir = os.getenv("OUT_DIR", "open_positions")
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, f"{provider_id}.json")

    payload = {
        "provider_id": provider_id,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "data": positions,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Saved: {out_path}")

if __name__ == "__main__":
    main()
