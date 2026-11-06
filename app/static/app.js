// Secret Santa frontend — vanilla JS, talks to the FastAPI backend.
"use strict";

const $ = (s) => document.querySelector(s);

let state = null;
let settingsBound = false;
let flashTimer = null;

// ---------- plumbing ----------

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return res.json();
}

async function refresh() {
  state = await api("/api/state");
  render();
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function flash(msg, isError = false) {
  const el = $("#flash");
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => { el.hidden = true; }, 6000);
}

function render() {
  renderGmail();
  renderParticipants();
  renderSettings();
  renderDraw();
}

// ---------- Gmail bar ----------

function renderGmail() {
  const bar = $("#gmail-bar");
  if (state.gmail_connected) {
    bar.innerHTML =
      `✅ Gmail connected as <b>${esc(state.gmail_account || "your account")}</b> ` +
      `<button id="disconnect" class="ghost small" type="button">Disconnect</button>`;
    $("#disconnect").onclick = async () => {
      if (!confirm("Disconnect Gmail? You'll need to authorise again before sending.")) return;
      try {
        await api("/api/auth/disconnect", { method: "POST" });
        await refresh();
      } catch (e) { flash(e.message, true); }
    };
  } else {
    bar.innerHTML =
      `⚠️ Gmail not connected — emails can't be sent yet. ` +
      `<button id="connect" type="button">Connect Gmail</button>`;
    // The whole tab goes to Google and comes back (works in Docker too —
    // the browser does the round-trip, the app just receives the callback).
    $("#connect").onclick = () => {
      flash("Opening Google sign-in in this tab…");
      window.location.href = "/auth/gmail/start";
    };
  }
}

// ---------- participants ----------

function renderParticipants() {
  const list = $("#participants-list");
  $("#p-count").textContent = state.participants.length ? `(${state.participants.length})` : "";
  if (!state.participants.length) {
    list.innerHTML = `<p class="muted">Nobody yet — add the first participant below.</p>`;
    return;
  }

  list.innerHTML = "";
  for (const p of state.participants) {
    const row = document.createElement("div");
    row.className = "person-row";
    row.innerHTML =
      `<span class="p-name" title="${esc(p.name)}">${esc(p.name)}</span>` +
      `<span class="p-email" title="${esc(p.email)}">${esc(p.email)}</span>`;

    // Multi-select: people this person must NOT draw (must not give to).
    const others = state.participants
      .filter((q) => q.id !== p.id)
      .sort((a, b) => a.name.localeCompare(b.name));
    const sel = document.createElement("select");
    sel.className = "excl";
    sel.multiple = true;
    sel.size = Math.min(4, others.length || 1);
    sel.title = `People ${p.name} should NOT draw (Ctrl/Cmd-click for several)`;
    for (const q of others) {
      const opt = document.createElement("option");
      opt.value = q.id;
      opt.textContent = q.name;
      opt.selected = p.exclusions.includes(q.id);
      sel.appendChild(opt);
    }
    sel.onchange = async () => {
      const exclusions = [...sel.selectedOptions].map((o) => o.value);
      try {
        await api(`/api/participants/${p.id}`, {
          method: "PUT",
          body: JSON.stringify({ name: p.name, email: p.email, exclusions }),
        });
        await refresh();
        flash(`Exclusions updated for ${p.name}` +
          (state.assignments ? " — the old draw was cleared, draw again." : ""));
      } catch (e) {
        flash(e.message, true);
        await refresh().catch(() => {});
      }
    };
    row.appendChild(sel);

    const del = document.createElement("button");
    del.className = "ghost danger small";
    del.type = "button";
    del.textContent = "×";
    del.title = `Remove ${p.name}`;
    del.onclick = async () => {
      if (!confirm(`Remove ${p.name}?`)) return;
      try {
        await api(`/api/participants/${p.id}`, { method: "DELETE" });
        await refresh();
      } catch (e) { flash(e.message, true); }
    };
    row.appendChild(del);

    list.appendChild(row);
  }
}

$("#add-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const name = $("#add-name").value.trim();
  const email = $("#add-email").value.trim();
  if (!name || !email) return;
  try {
    await api("/api/participants", {
      method: "POST",
      body: JSON.stringify({ name, email }),
    });
    $("#add-name").value = "";
    $("#add-email").value = "";
    $("#add-name").focus();
    await refresh();
  } catch (e) {
    flash(e.message, true);
  }
});

// ---------- email settings (inputs are bound once, so refreshes never wipe typing) ----------

function renderSettings() {
  if (settingsBound) return;
  settingsBound = true;
  const s = state.settings;
  $("#set-subject").value = s.subject;
  $("#set-spend").value = s.max_spend;
  $("#set-currency").value = s.currency;
  $("#set-notes").value = s.notes;
  $("#set-norecip").checked = !!s.no_reciprocal;

  $("#save-settings").onclick = async () => {
    try {
      await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify({
          subject: $("#set-subject").value,
          max_spend: $("#set-spend").value,
          currency: $("#set-currency").value,
          notes: $("#set-notes").value,
          no_reciprocal: $("#set-norecip").checked,
        }),
      });
      state = await api("/api/state");
      render();
      flash("Email settings saved.");
    } catch (e) { flash(e.message, true); }
  };
}

// ---------- draw & send ----------

function renderDraw() {
  const actions = $("#draw-actions");
  const preview = $("#preview");
  const sendSection = $("#send-section");
  const n = state.participants.length;

  if (!state.assignments) {
    sendSection.hidden = true;
    preview.innerHTML = "";
    if (n < 2) {
      actions.innerHTML = `<p class="muted">Add at least two participants to draw.</p>`;
      return;
    }
    actions.innerHTML = `<button id="draw-btn" type="button">🎲 Draw names</button>`;
    $("#draw-btn").onclick = async () => {
      try {
        await api("/api/draw", { method: "POST" });
        await refresh();
        flash("Draw complete — check the preview, then send.");
      } catch (e) { flash(e.message, true); }
    };
    return;
  }

  // ---- assignments exist ----
  const byId = Object.fromEntries(state.participants.map((p) => [p.id, p]));
  const entries = Object.entries(state.assignments)
    .map(([giver, recipient]) => [byId[giver], byId[recipient]])
    .filter(([g, r]) => g && r)
    .sort((a, b) => a[0].name.localeCompare(b[0].name));

  actions.innerHTML =
    `<span class="muted">Draw complete — you can see below who draws who (keep it secret!).</span>` +
    `<button id="redraw" class="ghost" type="button">Re-draw</button>`;
  preview.innerHTML =
    `<table class="preview"><thead><tr><th>Gives a gift to</th><th>Recipient</th></tr></thead><tbody>` +
    entries.map(([g, r]) => `<tr><td>${esc(g.name)}</td><td>${esc(r.name)}</td></tr>`).join("") +
    `</tbody></table>`;

  $("#redraw").onclick = async () => {
    const alreadySent = Object.values(state.send_status || {}).includes("sent");
    const msg = alreadySent
      ? "Some emails have ALREADY BEEN SENT. Re-drawing changes the assignments. Continue?"
      : "Re-drawing changes all assignments. Continue?";
    if (!confirm(msg)) return;
    try {
      await api("/api/draw", { method: "POST" });
      await refresh();
    } catch (e) { flash(e.message, true); }
  };

  renderSend();
}

function renderSend() {
  $("#send-section").hidden = false;
  const actions = $("#send-actions");
  const status = state.send_status || {};
  const errors = state.send_errors || {};
  const entries = state.participants
    .map((p) => [p, status[p.id] || "pending", errors[p.id]])
    .sort((a, b) => a[0].name.localeCompare(b[0].name));

  const counts = { pending: 0, sending: 0, sent: 0, failed: 0 };
  for (const [, st] of entries) counts[st] = (counts[st] || 0) + 1;
  const remaining = counts.pending + counts.failed + (counts.sending || 0);
  const inFlight = (counts.sending || 0) > 0;

  if (inFlight) {
    actions.innerHTML =
      `<span class="muted">Sending… ${counts.sent}/${entries.length} done</span>`;
  } else if (remaining === 0) {
    actions.innerHTML =
      `✅ <span>All emails sent.</span> ` +
      `<button id="resend-all" class="ghost small" type="button">Re-send to everyone (duplicate!)</button>`;
    $("#resend-all").onclick = () => doSend(true);
  } else {
    const label = counts.failed > 0
      ? `📧 Send emails (${counts.failed} failed will be retried)`
      : `📧 Send emails (${remaining} to send)`;
    actions.innerHTML = `<button id="send-btn" type="button">${label}</button>`;
    $("#send-btn").onclick = () => doSend(false);
  }

  $("#send-status").innerHTML =
    `<thead><tr><th>Person</th><th>Email</th><th>Status</th><th class="muted">Details</th></tr></thead>` +
    `<tbody>` +
    entries.map(([p, st, err]) =>
      `<tr><td>${esc(p.name)}</td><td>${esc(p.email)}</td>` +
      `<td class="st-${esc(st)}">${statusLabel(st)}</td>` +
      `<td class="muted small">${err ? esc(err) : ""}</td></tr>`
    ).join("") +
    `</tbody>`;
}

function statusLabel(st) {
  return { pending: "waiting", sending: "sending…", sent: "✓ sent", failed: "✗ failed" }[st] || st;
}

async function doSend(force) {
  if (force && !confirm("This re-sends the email to EVERYONE, including people who already received it. Continue?")) {
    return;
  }
  const poll = setInterval(() => { refresh().catch(() => {}); }, 1500);
  try {
    await api("/api/send", { method: "POST", body: JSON.stringify({ force }) });
  } catch (e) {
    flash(e.message, true);
  }
  clearInterval(poll);
  await refresh().catch(() => {});
}

// ---------- go ----------

// Returning from the Google sign-in round-trip: the server bounces us back
// to /?connected=… (or /?gmail_error=…) — show it, then clean the URL.
const _params = new URLSearchParams(location.search);
const _oauthConnected = _params.get("connected");
const _oauthError = _params.get("gmail_error");
if (_oauthConnected || _oauthError) history.replaceState(null, "", "/");

refresh()
  .catch((e) => flash(e.message, true))
  .then(() => {
    if (_oauthConnected) flash(`Gmail connected as ${_oauthConnected}!`);
    else if (_oauthError) flash(_oauthError, true);
  });
