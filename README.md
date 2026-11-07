# Secret Santa

A small local web app that runs a Secret Santa draw and emails every
participant their assignment from your **Gmail account** — using the
**Gmail API with OAuth 2.0**, so no account password is ever needed or
stored.

- FastAPI backend + a plain HTML/JS frontend (no build step)
- Random derangement matcher with per-person exclusions (backtracking, so it
  handles 15–50 people with plenty of "don't draw" rules)
- Optional "avoid reciprocal pairs" (A draws B and B draws A)
- Configurable email: subject, max spend (e.g. £15), extra notes
- Everything persists to `data/state.json`, so you can close the laptop
  mid-run, and failed sends can be retried

## Quick start

```bash
cd secretsanta
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

Then open <http://127.0.0.1:8000>.

If you're running a fresh clone as the app author, set up the OAuth client
first (next section) — it's a one-time thing.

## Run with Docker

```bash
cd secretsanta
docker build -t secretsanta .
docker run -d --name secretsanta -p 8000:8000 -v secretsanta-data:/data secretsanta
```

Then open <http://localhost:8000>.

- **The published host port must be 8000** (`-p 8000:8000`): after
  authorising on Google, the browser is redirected to
  `http://localhost:8000/auth/gmail/callback` to finish the connection.
- The **`/data` volume** holds `state.json` (the draw) and `tokens.json`
  (the Gmail authorisation). Keep it — otherwise a recreated container
  loses the draw and makes the user re-authorise Gmail.
- To use your own OAuth client instead of the bundled one:
  `docker run … -e GMAIL_OAUTH_CLIENT_ID=<client-id>`.

## OAuth client setup (one-time, ~5 minutes)

The app sends mail through the [Gmail API](https://developers.google.com/gmail/api)
using OAuth, with an OAuth **client that ships inside the app** — so end
users never need a Google Cloud account or a `client_secret.json`. They
just click **Connect Gmail** and sign in with their own account.

As the *app author*, you set up the client once:

1. **Create a project**
   Open [Google Cloud Console](https://console.cloud.google.com), pick or
   create a project (e.g. "secret-santa").

2. **Enable the Gmail API**
   *APIs & Services → Library → "Gmail API" → Enable*.

3. **Configure the OAuth consent screen**
   *APIs & Services → OAuth consent screen*:
   - User type: **External**
   - App name: anything (e.g. "Secret Santa")
   - User support email: your Gmail address
   - Publishing status:
     - **Testing** is fine to try it yourself — but only accounts you add
       under *Test users* can authorise, and tokens expire after **7 days**.
     - For real users, switch to **Published** (with only the `gmail.send`
       scope, Google verification is *not* required).

4. **Create the OAuth client**
   *APIs & Services → Credentials → Create credentials → OAuth client ID*:
   - Application type: **Desktop app**
   - Copy the **Client ID** (looks like `12345-abcdef.apps.googleusercontent.com`).
   - There is no client *secret* for desktop clients — the ID is a public
     identifier, safe to ship with the app.

5. **Put the ID in the app** — one of:
   - paste it into `DEFAULT_CLIENT_ID` in `app/config.py` — baked in for
     everyone (the zero-config option), or
   - set `GMAIL_OAUTH_CLIENT_ID` at runtime (e.g. `docker run -e …`), which
     overrides the bundled default.

   (`tokens.json` — the stored authorisation — is created automatically in
   the data directory after the first connect and is gitignored.)

### First run

1. Start the app, add participants, make your draw.
2. Click **Connect Gmail** at the top — the tab goes to Google's sign-in,
   sign in with the Gmail account you want to send from, and accept the
   `gmail.send` permission (if the app is in Testing mode you may get a
   "Google hasn't verified this app" warning — click *Advanced → Continue*).
   The app loads back automatically with the connection made.
3. The header should now show **Gmail connected as you@gmail.com**.

Emails are sent from the account you authorised — that's the "FROM" address
recipients will see.

## Usage

1. **Participants** — add name + email for everyone. Pick a name in each
   row's dropdown to mark "X should not draw that person"; excluded names
   pop out to the side as chips — click ✕ on a chip to allow them again.
   You can't exclude *everyone* for one person (no valid draw would be
   possible), and whenever the current exclusions can't be drawn the
   **Draw names** button is disabled with an explanation.
2. **Email** — set the subject, max spend, currency and any notes; tick
   "avoid reciprocal pairs" if you want. Save.
3. **Draw names** — the app assigns everyone a distinct recipient, respects
   the exclusions, and shows you a private preview.
4. **Send emails** — one email per person, only revealing *their* assignment.
   Progress updates live; each email is recorded as sent/failed as it goes.
   If some fail, just click **Send emails** again — only the unsent/failed
   ones go out.

## Privacy

- Each participant's email only contains their own assignment.
- `data/state.json` (or the `/data` volume in Docker) contains the full draw
  and everyone's emails — it lives on your machine only and is gitignored.
  Delete it after the event if you like.
- By default the app binds to `127.0.0.1` only, so it's not reachable from
  your network. (In Docker it listens on all interfaces, so protect the port
  yourself — e.g. run it on a machine only you can reach.)

## How the email sending works

- `app/mailer.py` uses `google-auth-oauthlib`'s `InstalledAppFlow` with the
  bundled OAuth client ID (no per-user `client_secret.json`). "Connect Gmail"
  redirects the browser to Google, which bounces it back to
  `http://localhost:<port>/auth/gmail/callback`; the app exchanges the
  authorization code (with PKCE) and saves the token — including a long-lived
  refresh token — to `tokens.json` in the data directory.
- Sending calls `gmail.users.messages.send(userId="me")` with a base64url
  RFC-2822 message (HTML + plain-text alternative), one call per person.
- The access token lasts an hour; when it expires the app silently refreshes
  it with the stored refresh token — which is why there's no password
  anywhere.

## Troubleshooting

- **"Gmail OAuth is not configured"** — you haven't set a client ID yet:
  paste one into `DEFAULT_CLIENT_ID` in `app/config.py` or set
  `GMAIL_OAUTH_CLIENT_ID` (see "OAuth client setup").
- **Authorisation fails with an access error** — your account isn't in the
  consent screen's *Test users* (or you're signed into a different Google
  account in the browser).
- **Docker: the callback never arrives / "state mismatch"** — the published
  host port must be 8000 (`-p 8000:8000`); the browser is redirected to
  `http://localhost:8000/auth/gmail/callback` to finish.
- **"Invalid Grant" after a while** — Testing-mode token expiry (7 days);
  click Connect Gmail again.
- **An email is marked failed** — the per-recipient error is shown in the
  status table (usually a bad address); fix the email and click Send again.
