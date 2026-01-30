import os
import sys
import json
import requests
from datetime import datetime, timezone
from typing import Any, Optional

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
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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


def extract_positions_map(data_wrapper: Any) -> dict[int, str]:
    """
    Expects wrapper: {"data": {"openPositions": [ {"ticket":..., "symbol":...}, ... ]}}
    Returns: {ticket:int -> symbol:str}
    """
    if not isinstance(data_wrapper, dict):
        return {}
    data = data_wrapper.get("data")
    if not isinstance(data, dict):
        return {}
    ops = data.get("openPositions")
    if not isinstance(ops, list):
        return {}

    m: dict[int, str] = {}
    for p in ops:
        if not isinstance(p, dict) or "ticket" not in p:
            continue
        try:
            ticket = int(p["ticket"])
        except (TypeError, ValueError):
            continue
        symbol = p.get("symbol") or "UNKNOWN"
        m[ticket] = str(symbol)
    return m


def build_message(provider_id: str, old_map: dict[int, str], new_map: dict[int, str], payload_data: dict) -> str:
    old_ids = set(old_map.keys())
    new_ids = set(new_map.keys())

    added_ids = sorted(new_ids - old_ids)
    removed_ids = sorted(old_ids - new_ids)

    def fmt(items: list[int], src: dict[int, str]) -> str:
        return ", ".join([f"{i} ({src.get(i, 'UNKNOWN')})" for i in items])

    total_netpl = payload_data.get("totalNetPL")
    pips = payload_data.get("pips")
    size = payload_data.get("size")

    lines: list[str] = []
    lines.append("✅ <b>Open Positions Update</b>")
    lines.append(f"Provider: <code>{html_escape(provider_id)}</code>")
    lines.append(f"Time (UTC): <code>{datetime.now(timezone.utc).isoformat()}</code>")
    lines.append("")
    lines.append(f"Open positions: <b>{len(new_ids)}</b>")

    if added_ids:
        lines.append(f"➕ Added: <code>{html_escape(fmt(added_ids, new_map))}</code>")
    if removed_ids:
        lines.append(f"➖ Removed: <code>{html_escape(fmt(removed_ids, old_map))}</code>")

    if not added_ids and not removed_ids:
        lines.append("No ticket changes detected.")

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

    new_map = extract_positions_map({"data": new_file_obj["data"]})

    existing = read_existing_payload(out_path)
    old_map = extract_positions_map(existing) if existing else {}

    # Compare only ticket IDs
    if existing and set(new_map.keys()) == set(old_map.keys()):
        print(f"No ticket changes for provider {provider_id}. Not saving.")
        sys.exit(0)

    # Save (only when changed OR first run)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(new_file_obj, f, ensure_ascii=False, indent=2)
    print(f"Saved: {out_path}")

    # Telegram notify (only if TG vars provided)
    if tg_token and tg_chat_id:
        msg = build_message(provider_id, old_map, new_map, new_file_obj["data"])
        send_telegram_html(tg_token, tg_chat_id, msg)
        print("Telegram notification sent.")


if __name__ == "__main__":
    main()
