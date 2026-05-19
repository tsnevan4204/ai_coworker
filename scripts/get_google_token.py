"""One-time OAuth flow to obtain GOOGLE_REFRESH_TOKEN for .env."""

from __future__ import annotations

import os

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def main() -> None:
    client_secrets = os.environ.get("GOOGLE_CLIENT_SECRETS_FILE", "credentials.json")
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
    creds = flow.run_local_server(port=0)
    print("\nAdd to .env:\n")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
