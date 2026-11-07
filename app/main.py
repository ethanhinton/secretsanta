"""FastAPI application: API routes + the static frontend."""
from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

from . import config, mailer, state as store
from .matcher import draw_names
from .models import AppState, DrawSettings, Participant, new_id
from .templates import build_email

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Atomicity of load→modify→save on state.json.
_state_lock = threading.Lock()
# Serialises long-running operations (Gmail connect / send batch).
_busy_lock = threading.Lock()


# ---------- request schemas ----------

class ParticipantIn(BaseModel):
    name: str
    email: EmailStr
    exclusions: list[str] = []


class SettingsIn(BaseModel):
    subject: str = "Secret Santa draw! (DO NOT REPLY)"
    max_spend: str = ""
    currency: str = "£"
    notes: str = ""
    no_reciprocal: bool = False


class SendIn(BaseModel):
    # False (default): send only to people not already marked "sent"
    # (i.e. pending + failed — this is how you retry failures).
    # True: re-send to everyone, even those already sent.
    force: bool = False


# ---------- helpers ----------

def _find(state: AppState, pid: str) -> Participant:
    for p in state.participants:
        if p.id == pid:
            return p
    raise HTTPException(404, "Participant not found.")


def _excludes_everyone(others: set, exclusions: list) -> bool:
    """True if exclusions cover every other participant. That person would
    have nobody left to draw — a state no valid draw can ever use, so we
    refuse to create it rather than just warn about it later."""
    return bool(others) and others <= set(exclusions)


def _invalidate_draw(state: AppState) -> None:
    """Participant list / exclusions changed → the old draw is void."""
    state.assignments = None
    state.send_status = {}
    state.send_errors = {}


def _state_out(state: AppState) -> dict:
    return {
        "participants": [
            {"id": p.id, "name": p.name, "email": p.email, "exclusions": p.exclusions}
            for p in state.participants
        ],
        "settings": state.settings.__dict__,
        "assignments": state.assignments,
        "send_status": state.send_status,
        "send_errors": state.send_errors,
        "gmail_account": state.gmail_account,
        "gmail_connected": mailer.token_exists(),
    }


def _mark(pid: str, status: str, error: Optional[str] = None) -> None:
    with _state_lock:
        state = store.load_state()
        state.send_status[pid] = status
        if error:
            state.send_errors[pid] = error
        else:
            state.send_errors.pop(pid, None)
        store.save_state(state)


def _normalize_statuses() -> None:
    """On startup, in-flight sends are over: 'sending' → 'pending'."""
    with _state_lock:
        state = store.load_state()
        changed = False
        for key, value in list(state.send_status.items()):
            if value == "sending":
                state.send_status[key] = "pending"
                changed = True
        if changed:
            store.save_state(state)


@asynccontextmanager
async def lifespan(_: FastAPI):
    config.migrate_legacy_tokens()
    _normalize_statuses()
    yield


app = FastAPI(title="Secret Santa", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------- routes ----------

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/state")
def get_state():
    with _state_lock:
        state = store.load_state()
    return _state_out(state)


@app.post("/api/participants", status_code=201)
def add_participant(body: ParticipantIn):
    if not body.name.strip():
        raise HTTPException(400, "Name is required.")
    with _state_lock:
        state = store.load_state()
        if any(p.email.lower() == body.email.lower() for p in state.participants):
            raise HTTPException(409, "A participant with that email already exists.")
        valid_ids = {p.id for p in state.participants}
        new_exclusions = [e for e in body.exclusions if e in valid_ids]
        if _excludes_everyone(valid_ids, new_exclusions):
            raise HTTPException(
                400,
                f"Can't exclude everyone for {body.name.strip()} — "
                "they'd have nobody to draw.",
            )
        p = Participant(
            id=new_id(),
            name=body.name.strip(),
            email=str(body.email),
            exclusions=new_exclusions,
        )
        state.participants.append(p)
        _invalidate_draw(state)
        store.save_state(state)
    return _state_out(state)


@app.put("/api/participants/{pid}")
def update_participant(pid: str, body: ParticipantIn):
    if not body.name.strip():
        raise HTTPException(400, "Name is required.")
    with _state_lock:
        state = store.load_state()
        p = _find(state, pid)
        if any(
            other.email.lower() == body.email.lower() and other.id != pid
            for other in state.participants
        ):
            raise HTTPException(409, "Another participant already uses that email.")
        valid_ids = {q.id for q in state.participants} - {pid}
        new_exclusions = [e for e in body.exclusions if e in valid_ids]
        if _excludes_everyone(valid_ids, new_exclusions):
            raise HTTPException(
                400,
                f"{body.name.strip()} can't exclude everyone — "
                "they'd have nobody to draw.",
            )
        exclusions_changed = set(new_exclusions) != set(p.exclusions)
        p.name = body.name.strip()
        p.email = str(body.email)
        p.exclusions = new_exclusions
        if exclusions_changed:
            _invalidate_draw(state)
        store.save_state(state)
    return _state_out(state)


@app.delete("/api/participants/{pid}")
def delete_participant(pid: str):
    with _state_lock:
        state = store.load_state()
        _find(state, pid)  # 404 if unknown
        state.participants = [p for p in state.participants if p.id != pid]
        for p in state.participants:
            p.exclusions = [e for e in p.exclusions if e != pid]
        _invalidate_draw(state)
        store.save_state(state)
    return _state_out(state)


@app.put("/api/settings")
def update_settings(body: SettingsIn):
    with _state_lock:
        state = store.load_state()
        state.settings = DrawSettings(**body.model_dump())
        store.save_state(state)
    return _state_out(state)


@app.post("/api/draw")
def draw():
    with _state_lock:
        state = store.load_state()
        if len(state.participants) < 2:
            raise HTTPException(400, "Add at least two participants before drawing.")
        try:
            assignments = draw_names(state.participants, state.settings.no_reciprocal)
        except ValueError as e:
            raise HTTPException(422, str(e))
        state.assignments = assignments
        state.send_status = {}
        state.send_errors = {}
        store.save_state(state)
    return _state_out(state)


@app.get("/api/check-draw")
def check_draw():
    """Can a valid draw be made with the current participants/exclusions?

    Runs the same matcher as /api/draw but commits nothing. The frontend
    calls this after setup changes so it can warn (and disable the draw
    button) before the user tries to draw.
    """
    with _state_lock:
        state = store.load_state()
    try:
        draw_names(state.participants, state.settings.no_reciprocal)
    except ValueError as e:
        return {"feasible": False, "reason": str(e)}
    return {"feasible": True, "reason": ""}


@app.get("/auth/gmail/start")
def auth_gmail_start():
    """Redirect the user's browser to Google's sign-in/consent page."""
    try:
        url, st = mailer.start_connect()
    except mailer.GmailNotConfiguredError as e:
        return HTMLResponse(
            "<html><body><h1>Gmail not configured</h1><p>"
            f"{e}</p><p><a href='/'>Back to Secret Santa</a></p></body></html>",
            status_code=500,
        )
    resp = RedirectResponse(url, status_code=302)
    # Remember this round-trip's state so the callback can verify it came
    # from us (stop stray/CSRF callbacks).
    resp.set_cookie(
        "oauth_state", st,
        max_age=mailer.AUTH_TTL_SECONDS, httponly=True, samesite="lax",
    )
    return resp


def _oauth_done(account: str = "", error: str = ""):
    """Redirect back to the UI, carrying a flash message via query params."""
    if account:
        url = f"/?connected={quote(account)}"
    elif error:
        url = f"/?gmail_error={quote(error)}"
    else:
        url = "/"
    resp = RedirectResponse(url, status_code=302)
    resp.delete_cookie("oauth_state")
    return resp


@app.get("/auth/gmail/callback")
def auth_gmail_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    """Google bounces the user's browser here after sign-in.

    On success the token is stored and the browser is sent back to the UI
    with a ``?connected=...`` flash; on failure with ``?gmail_error=...``.
    """
    if error:
        return _oauth_done(error=f"Google sign-in was not completed ({error}).")
    if not code or request.cookies.get("oauth_state", "") != state:
        return _oauth_done(error="Authorisation failed (state mismatch) — try connecting again.")
    if not _busy_lock.acquire(blocking=False):
        return _oauth_done(
            error="The app is busy right now (an email send is running) — try connecting in a moment."
        )
    try:
        try:
            account = mailer.complete_connect(code, state)
        except (mailer.GmailAuthError, mailer.GmailNotConfiguredError) as e:
            return _oauth_done(error=str(e))
        with _state_lock:
            st = store.load_state()
            st.gmail_account = account or st.gmail_account
            store.save_state(st)
        return _oauth_done(account=account)
    finally:
        _busy_lock.release()


@app.post("/api/auth/disconnect")
def auth_disconnect():
    mailer.disconnect()
    with _state_lock:
        state = store.load_state()
        state.gmail_account = None
        store.save_state(state)
    return _state_out(state)


@app.post("/api/send")
def send(body: SendIn = SendIn()):
    """Send the draw emails. Blocks until the whole batch is done.

    Per-recipient progress is persisted after every email, so a crash or
    failure mid-batch can be resumed by calling this again (it only sends
    to participants not already marked "sent").
    """
    if not _busy_lock.acquire(blocking=False):
        raise HTTPException(409, "Gmail is busy — a connect or send is already running.")
    try:
        return _do_send(body.force)
    finally:
        _busy_lock.release()


def _do_send(force: bool) -> dict:
    try:
        service = mailer.get_service()
    except (mailer.GmailNotConfiguredError, mailer.GmailNotConnectedError) as e:
        raise HTTPException(400, str(e))

    with _state_lock:
        state = store.load_state()
    if not state.assignments:
        raise HTTPException(400, "Draw names first — there is nothing to send.")

    targets = [
        p for p in state.participants
        if force or state.send_status.get(p.id, "pending") != "sent"
    ]
    if not targets:
        return {"sent": 0, "results": {}}

    by_id = {p.id: p for p in state.participants}

    # Mark all targets as "sending" up front so the UI can show progress.
    with _state_lock:
        state = store.load_state()
        for p in targets:
            state.send_status[p.id] = "sending"
            state.send_errors.pop(p.id, None)
        store.save_state(state)

    results: dict = {}
    for p in targets:
        # Re-check in case the participant was removed mid-batch.
        with _state_lock:
            state = store.load_state()
            if p.id not in {q.id for q in state.participants}:
                results[p.id] = "skipped (removed)"
                continue
            assignments = state.assignments or {}
            settings = state.settings
        drawn = by_id.get(assignments.get(p.id, ""))
        if drawn is None:
            _mark(p.id, "failed", "Missing assignment data.")
            results[p.id] = "failed: missing assignment data"
            continue
        subject, html_body, text_body = build_email(p.name, drawn.name, settings)
        try:
            mailer.send_email(service, to_email=p.email, subject=subject,
                              html=html_body, text=text_body)
            _mark(p.id, "sent")
            results[p.id] = "sent"
        except Exception as e:  # report per-recipient, keep going
            _mark(p.id, "failed", str(e))
            results[p.id] = f"failed: {e}"
        time.sleep(0.3)  # small politeness delay between sends

    return {"sent": sum(1 for v in results.values() if v == "sent"), "results": results}
