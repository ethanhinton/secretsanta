"""Sending via the Gmail API with OAuth 2.0.

The app ships with its own OAuth *client* (a public identifier — see
``config.DEFAULT_CLIENT_ID`` or the ``GMAIL_OAUTH_CLIENT_ID`` env var), so
end users never create a Google Cloud project or a ``client_secret.json``:
they click "Connect Gmail", sign in to their own Google account, and a
refresh token is stored in ``tokens.json`` (in the data directory). From
then on the access token is refreshed silently in the background — no
account password is ever needed or stored.

The bundled client is normally a "Desktop app" (no secret). It also works
with a "Web application" client, which has a secret: supply it via
``GMAIL_OAUTH_CLIENT_SECRET`` so the token exchange can present it to
Google (see ``_build_flow``).

The authorisation is a standard web callback round-trip, which also works
when the app runs in a Docker container (no browser or local port needed
on the app side):

  1. ``GET /auth/gmail/start`` → :func:`start_connect` builds Google's
     authorisation URL; the API layer redirects the user's browser there.
  2. The user signs in and grants ``gmail.send`` (the only scope requested).
  3. Google bounces the browser back to
     ``http://localhost:<PORT>/auth/gmail/callback?code=...&state=...``.
  4. ``GET /auth/gmail/callback`` → :func:`complete_connect` exchanges the
     code for a token, stores it, and learns the account's email address.

PKCE is used throughout; the per-authorisation code verifier lives in
memory, keyed by the OAuth ``state`` value (the API layer additionally
checks that ``state`` against a cookie, to stop stray callbacks).
"""
from __future__ import annotations

import base64
import json
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from . import config

# Narrowest useful scope: send mail, nothing else. ``openid`` +
# ``userinfo.email`` are added only so the app can learn *which* account
# connected (from the ID token) — the gmail.send scope alone cannot call
# users.getProfile.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

# How long an in-flight authorisation (start → callback) may take.
AUTH_TTL_SECONDS = 600
_CALLBACK_PATH = "/auth/gmail/callback"

# In-flight authorisations: state → {code_verifier, expires}. Single-process
# app, so a plain dict is fine; each process only sees its own callbacks.
_pending_auths: dict[str, dict[str, Any]] = {}


class GmailNotConfiguredError(RuntimeError):
    """No usable OAuth client ID — see config / README."""


class GmailAuthError(RuntimeError):
    """The authorisation round-trip failed (denied, expired, bad code…)."""


class GmailNotConnectedError(RuntimeError):
    """No usable OAuth token — the user needs to connect Gmail."""


def _config_message() -> str:
    return (
        "Gmail OAuth is not configured. Set the GMAIL_OAUTH_CLIENT_ID "
        "environment variable, or set DEFAULT_CLIENT_ID in app/config.py. "
        "Use a 'Desktop app' client (no secret), or a 'Web application' "
        "client together with GMAIL_OAUTH_CLIENT_SECRET (see README → "
        "'OAuth client setup')."
    )


def is_configured() -> bool:
    """Cheap local check used for UI status (no network call)."""
    return config.gmail_client_id().endswith(".apps.googleusercontent.com")


def token_exists() -> bool:
    """Cheap local check used for UI status (no network call)."""
    return config.TOKENS_FILE.exists()


def _callback_url() -> str:
    # Desktop-app clients allow http://localhost on ANY port, so no
    # registration is needed — only the published host port must match.
    return f"http://localhost:{config.PORT}{_CALLBACK_PATH}"


def _build_flow(autogenerate_code_verifier: bool = True) -> InstalledAppFlow:
    """Build the OAuth flow from the configured client ID (no JSON file).

    The dict is Google's "client secrets" format. "Desktop app" clients have
    no secret (``client_secret`` is ""), but "Web application" clients do —
    in that case ``GMAIL_OAUTH_CLIENT_SECRET`` supplies it, and the token
    exchange sends it to Google (see ``Flow.fetch_token``).
    """
    client_config = {
        "installed": {
            "client_id": config.gmail_client_id(),
            "client_secret": config.gmail_client_secret(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [f"http://localhost:{config.PORT}"],
        }
    }
    flow = InstalledAppFlow.from_client_config(
        client_config, SCOPES,
        autogenerate_code_verifier=autogenerate_code_verifier,
    )
    flow.redirect_uri = _callback_url()
    return flow


def _prune_pending() -> None:
    now = time.monotonic()
    for key in [k for k, v in _pending_auths.items() if now > v["expires"]]:
        _pending_auths.pop(key, None)


def start_connect() -> tuple[str, str]:
    """Begin the authorisation round-trip.

    Returns ``(auth_url, state)``. The API layer redirects the user's
    browser to ``auth_url`` and remembers ``state`` (cookie); Google
    bounces the browser back to the callback URL with the same ``state``.
    """
    if not is_configured():
        raise GmailNotConfiguredError(_config_message())
    flow = _build_flow()
    url, state = flow.authorization_url(prompt="consent")
    _prune_pending()
    _pending_auths[state] = {
        "code_verifier": flow.code_verifier,
        "expires": time.monotonic() + AUTH_TTL_SECONDS,
    }
    return url, state


def complete_connect(code: str, state: str) -> str:
    """Finish the round-trip: exchange the code, store the token.

    Returns the connected account's email address. Raises
    :class:`GmailAuthError` if the authorisation is unknown/expired or
    Google rejects the code.
    """
    if not is_configured():
        raise GmailNotConfiguredError(_config_message())
    _prune_pending()
    pending = _pending_auths.pop(state, None)
    if pending is None:
        raise GmailAuthError(
            "Authorisation is unknown or expired — click 'Connect Gmail' again."
        )

    # Rebuild a flow pinned to the code verifier issued in start_connect()
    # (PKCE: the exchange must use the same verifier as the authorisation).
    flow = _build_flow(autogenerate_code_verifier=False)
    flow.code_verifier = pending["code_verifier"]
    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
    except Exception as e:
        raise GmailAuthError(
            f"Google rejected the sign-in ({e}). Check that GMAIL_OAUTH_CLIENT_ID "
            "and (for a 'Web application' client) GMAIL_OAUTH_CLIENT_SECRET "
            "match your Google Cloud credentials, and that "
            "http://localhost:<port>/auth/gmail/callback is a registered "
            "authorized redirect URI for the client — then try again."
        ) from e
    if creds is None or not creds.token:
        raise GmailAuthError("Google did not return a token — try connecting again.")

    config.TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.TOKENS_FILE.write_text(creds.to_json())
    config.TOKENS_FILE.chmod(0o600)

    # Learn which account connected from the ID token (the gmail.send scope
    # alone cannot call users.getProfile). The ID token is a JWT: the
    # payload is the middle dot-separated segment, base64url-encoded JSON.
    account = ""
    id_token = getattr(creds, "id_token", None)
    if id_token:
        try:
            payload = id_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)  # pad to a multiple of 4
            claims = json.loads(base64.urlsafe_b64decode(payload))
            account = claims.get("email", "")
        except Exception:
            account = ""
    return account


def _load_credentials() -> Optional[Credentials]:
    """Load (and if needed refresh) the stored token. None if unusable."""
    if not config.TOKENS_FILE.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(config.TOKENS_FILE), SCOPES)
    if creds is None or (not creds.token and not creds.refresh_token):
        return None
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(google.auth.transport.requests.Request())
            config.TOKENS_FILE.write_text(creds.to_json())
        except Exception:
            # Refresh token expired/revoked (e.g. OAuth app still in
            # "Testing" mode, where tokens expire after 7 days).
            return None
    return creds if creds.valid else None


def get_service() -> Any:
    """Return a Gmail API service, or raise a descriptive error."""
    if not is_configured():
        raise GmailNotConfiguredError(_config_message())
    creds = _load_credentials()
    if creds is None:
        raise GmailNotConnectedError(
            "Gmail is not connected yet — click 'Connect Gmail' first."
        )
    return build("gmail", "v1", credentials=creds)


def disconnect() -> None:
    """Forget the stored token. (The authorisation itself can be revoked in
    Google Account settings → Security → Third-party access if needed.)"""
    config.TOKENS_FILE.unlink(missing_ok=True)


def send_email(service: Any, to_email: str, subject: str, html: str, text: str) -> None:
    """Send one email from the connected account (userId='me').

    The From address is the connected account itself — that's how the
    Gmail API works when sending on behalf of the signed-in user.
    """
    msg = MIMEMultipart("alternative")
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
