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

def extract_tickets(data_wrapper: Any) -> List[int]:
    """
    Expects wrapper: {"data": { ... openPositions: [ {ticket:...}, ... ] }}
    Returns sorted list of ticket ints.
    """
    if not isinstance(data_wrapper, dict):
        return []
    data = data_wrapper.get("data")
    if not isinstance(data, dict):
        return []
    ops = data.get("openPositions")
    if not isinstance(ops, list):
        return []
    tickets: List[int] = []
    for p in ops:
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

def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )

def send_telegram_html(bot_token: str, chat_id: str, html: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    r = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    r.raise_for_status()

def build_message(provider_id: str, old_tickets: List[int], new_tickets: List[int], payload_data: dict) -> str:
    added = [t for t in new_tickets if t not in old_tickets]
    removed = [t for t in old_tickets if t not in new_tickets]

    total_netpl = payload_data.get("totalNetPL")
    pips = payload_data.get("pips")
    size = payload_data.get("size")

    lines = []
    lines.append("✅ <b>Open Positions Update</b>")
    lines.append(f"Provider: <code>{html_escape(provider_id)}</code>")
    lines.append(f"Time (UTC): <code>{datetime.now(timezone.utc).isoformat()}</code>")
    lines.append("")
    lines.append(f"Tickets: <b>{len(new_tickets)}</b>")
    if added:
        lines.append(f"➕ Added: <code>{', '.join(map(str, added))}</code>")
    if removed:
        lines.append(f"➖ Removed: <code>{', '.join(map(str, removed))}</code>")
    lines.append("")
    lines.append("Snapshot:")
    lines.append(f"• totalNetPL: <code>{html_escape(str(total_netpl))}</code>")
    lines.append(f"• pips: <code>{html_escape(str(pips))}</code>")
    lines.append(f"• size: <code>{html_escape(str(size))}</code>")

    return "\n".join(lines)

def main():
    email = require_env("FA_EMAIL")
    password = require_env("FA_PASSWORD")
    provider_id = os.getenv("PROVIDER_ID", "931")

    out_dir = os.getenv("OUT_DIR", "open_positions")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{provider_id}.json")

    tg_token = os.getenv("TG_BOT_TOKEN")  # optional
    tg_chat_id = os.getenv("TG_CHAT_ID")  # optional

    token = signin_and_get_token(email, password)
    api_resp = fetch_open_positions(provider_id, token)

    # Persist exactly like your current structure:
    new_file_obj = {
        "provider_id": str(provider_id),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "data": api_resp.get("data") if isinstance(api_resp, dict) and "data" in api_resp else api_resp,
    }

    new_tickets = extract_tickets({"data": new_file_obj["data"]})

    existing = read_existing_payload(out_path)
    old_tickets = extract_tickets(existing) if existing else []

    if existing and new_tickets == old_tickets:
        print(f"No ticket changes for provider {provider_id}. Not saving.")
        sys.exit(0)

    # Save (only when changed OR first run)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(new_file_obj, f, ensure_ascii=False, indent=2)
    print(f"Saved: {out_path}")

    # Telegram notify (only if TG vars provided)
    if tg_token and tg_chat_id:
        msg = build_message(provider_id, old_tickets, new_tickets, new_file_obj["data"])
        send_telegram_html(tg_token, tg_chat_id, msg)
        print("Telegram notification sent.")

if __name__ == "__main__":
    main()
