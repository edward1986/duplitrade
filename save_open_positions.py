import os
import sys
import json
import requests
from datetime import datetime, timezone
from typing import Any, Optional, List

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

    data = r.json()
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

def fetch_open_positions(provider_id: str, token: str) -> Any:
    r = requests.get(
        OPEN_POSITIONS_URL,
        params={"provider_id": provider_id},
        headers={"Accept": "application/json", "token": token},
        timeout=30,
    )
    if not r.ok:
        print("Open positions failed:", r.status_code, r.text, file=sys.stderr)
        sys.exit(1)
    try:
        return r.json()
    except ValueError:
        return {"raw": r.text}

def extract_tickets(api_payload: Any) -> List[int]:
    """
    Extracts tickets from: data.openPositions[].ticket
    Returns a sorted list of ints (order-insensitive compare).
    """
    if not isinstance(api_payload, dict):
        return []

    data = api_payload.get("data")
    if not isinstance(data, dict):
        return []

    open_positions = data.get("openPositions")
    if not isinstance(open_positions, list):
        return []

    tickets: List[int] = []
    for p in open_positions:
        if isinstance(p, dict) and "ticket" in p:
            try:
                tickets.append(int(p["ticket"]))
            except (TypeError, ValueError):
                pass

    tickets.sort()
    return tickets

def read_existing_payload(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

def main():
    email = require_env("FA_EMAIL")
    password = require_env("FA_PASSWORD")
    provider_id = os.getenv("PROVIDER_ID", "931")
    out_dir = os.getenv("OUT_DIR", "open_positions")
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, f"{provider_id}.json")

    token = signin_and_get_token(email, password)
    new_payload = fetch_open_positions(provider_id, token)

    # Wrap in your persisted structure (same as your example)
    new_file_obj = {
        "provider_id": str(provider_id),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "data": new_payload.get("data") if isinstance(new_payload, dict) and "data" in new_payload else new_payload,
    }

    new_tickets = extract_tickets({"data": new_file_obj["data"]})

    existing = read_existing_payload(out_path)
    if existing:
        old_tickets = extract_tickets(existing)
        if new_tickets == old_tickets:
            print(f"No ticket changes for provider {provider_id}. Not saving.")
            sys.exit(0)
        print(f"Tickets changed for provider {provider_id}: old={old_tickets} new={new_tickets}. Saving update.")
    else:
        print(f"No existing file for provider {provider_id}. Saving first snapshot.")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(new_file_obj, f, ensure_ascii=False, indent=2)

    print(f"Saved: {out_path}")

if __name__ == "__main__":
    main()
