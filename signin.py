# signin.py
import os
import json
import sys
import requests

URL = "https://fa.new.duplitrade.com/api/auth/signin"

def main():
    email = os.getenv("FA_EMAIL")
    password = os.getenv("FA_PASSWORD")

    if not email or not password:
        print("Missing env vars: FA_EMAIL and/or FA_PASSWORD", file=sys.stderr)
        sys.exit(2)

    payload = {"email": email, "password": password}

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        r = requests.post(URL, headers=headers, json=payload, timeout=30)
    except requests.RequestException as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("Status:", r.status_code)

    # Try JSON output, fallback to raw text
    try:
        data = r.json()
        # Avoid printing tokens accidentally if the API returns them
        safe = {k: ("<redacted>" if "token" in k.lower() else v) for k, v in data.items()}
        print(json.dumps(safe, indent=2))
    except ValueError:
        print(r.text)

    # Non-2xx should fail the run
    if not r.ok:
        sys.exit(1)

if __name__ == "__main__":
    main()
