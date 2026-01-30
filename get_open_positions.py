# get_open_positions.py
import os
import sys
import requests

SIGNIN_URL = "https://fa.new.duplitrade.com/api/auth/signin"
OPEN_POSITIONS_URL = "https://fa.new.duplitrade.com/api/user/get_provider_open_positions"

def require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        print(f"Missing env var: {name}", file=sys.stderr)
        sys.exit(2)
    return val

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

    # Common token keys to try (adjust if your API uses a different field)
    token = (
        data.get("token")
        or data.get("tokn")
        or data.get("access_token")
        or data.get("accessToken")
        or data.get("data", {}).get("token")
    )

    if not token:
        print("Could not find token in signin response keys:", list(data.keys()), file=sys.stderr)
        print("Full JSON:", data, file=sys.stderr)
        sys.exit(1)

    return token

def get_open_positions(provider_id: str, token: str) -> dict | list | str:
    r = requests.get(
        OPEN_POSITIONS_URL,
        params={"provider_id": provider_id},
        headers={
            "Accept": "application/json",
            "token": token,  # <-- header name exactly as you said
        },
        timeout=30,
    )

    if not r.ok:
        print("Open positions request failed:", r.status_code, r.text, file=sys.stderr)
        sys.exit(1)

    try:
        return r.json()
    except ValueError:
        return r.text

def main():
    email = require_env("FA_EMAIL")
    password = require_env("FA_PASSWORD")

    provider_id = os.getenv("PROVIDER_ID", "931")

    token = signin_and_get_token(email, password)
    result = get_open_positions(provider_id, token)

    # Print result (do NOT print token)
    print(result)

if __name__ == "__main__":
    main()
