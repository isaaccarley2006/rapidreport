import json
import os

import msal
import requests

import config

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["Mail.Read", "Mail.Send"]
TOKEN_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "token_cache.json")


def _get_msal_app():
    cache = msal.SerializableTokenCache()
    # Prefer env var token cache (for Railway/serverless), fall back to file
    env_cache = os.getenv("MS_TOKEN_CACHE")
    if env_cache:
        cache.deserialize(env_cache)
    elif os.path.exists(TOKEN_CACHE_PATH):
        with open(TOKEN_CACHE_PATH) as f:
            cache.deserialize(f.read())

    app = msal.PublicClientApplication(
        config.MS_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{config.MS_TENANT_ID}",
        token_cache=cache,
    )
    return app, cache


def _save_cache(cache):
    if cache.has_state_changed:
        os.makedirs(os.path.dirname(TOKEN_CACHE_PATH), exist_ok=True)
        with open(TOKEN_CACHE_PATH, "w") as f:
            f.write(cache.serialize())


def _get_token() -> str:
    app, cache = _get_msal_app()

    accounts = app.get_accounts()
    print(f"  [outlook] Found {len(accounts)} cached accounts, env cache set: {bool(os.getenv('MS_TOKEN_CACHE'))}")
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(cache)
            return result["access_token"]
        print(f"  [outlook] Silent auth failed: {result.get('error_description') if result else 'no result'}")

    # On Railway (no interactive terminal), don't attempt device flow
    if os.getenv("MS_TOKEN_CACHE"):
        raise RuntimeError(
            "Token cache expired or invalid. Re-authenticate locally and update "
            "the MS_TOKEN_CACHE env var in Railway."
        )

    # Device code flow for local/interactive auth
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow failed: {json.dumps(flow, indent=2)}")

    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"Auth failed: {result.get('error_description', result)}")

    _save_cache(cache)
    return result["access_token"]


def _auth_header():
    return {"Authorization": f"Bearer {_get_token()}"}


def get_emails(week_start_iso: str, week_end_iso: str) -> list[dict]:
    """Fetch received emails within the date range (ISO 8601 strings)."""
    url = f"{GRAPH_BASE}/me/messages"
    params = {
        "$filter": f"receivedDateTime ge {week_start_iso} and receivedDateTime le {week_end_iso}",
        "$select": "subject,from,receivedDateTime,bodyPreview",
        "$orderby": "receivedDateTime desc",
        "$top": 50,
    }

    all_emails = []
    while url:
        resp = requests.get(url, headers=_auth_header(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for m in data.get("value", []):
            all_emails.append(
                {
                    "subject": m.get("subject"),
                    "from": m.get("from", {}).get("emailAddress", {}).get("address"),
                    "date": m.get("receivedDateTime"),
                    "snippet": m.get("bodyPreview", "")[:200],
                }
            )
        url = data.get("@odata.nextLink")
        params = {}  # nextLink already contains query params

    return all_emails


def send_email(to: str, subject: str, html_body: str):
    """Send an email via Microsoft Graph."""
    url = f"{GRAPH_BASE}/me/sendMail"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
    }
    resp = requests.post(
        url,
        headers={**_auth_header(), "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
