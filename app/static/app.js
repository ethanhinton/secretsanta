// Secret Santa frontend — vanilla JS, talks to the FastAPI backend.
"use strict";

const $ = (s) => document.querySelector(s);

let state = null;
let settingsBound = false;
let flashTimer = null;
let drawCheck = null; // {feasible, reason} from /api/check-draw, or null while pending
let checkSeq = 0;

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
  // While there's no draw yet, verify the setup can actually be drawn —
  // the check runs the real matcher server-side and never commits.
  // (A hidden draw also reports assignments: null, so check the flag too.)
  if (!state.assignments && !state.hide_assignments && state.participants.length >= 2) {
    drawCheck = null;
    renderDraw();
    checkDraw();
  }
}

async function checkDraw() {
  const seq = ++checkSeq;
  try {
    drawCheck = await api("/api/check-draw");
  } catch (e) {
    drawCheck = { feasible: false, reason: `Couldn't verify the setup: ${e.message}` };
  }
  if (seq !== checkSeq) return; // a newer check superseded this one
  renderDraw();
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

  const byId = Object.fromEntries(state.participants.map((p) => [p.id, p]));
  list.innerHTML = "";
  for (const p of state.participants) {
    const row = document.createElement("div");
    row.className = "person-row";
    row.innerHTML =
      `<span class="p-name" title="${esc(p.name)}">${esc(p.name)}</span>` +
      `<span class="p-email" title="${esc(p.email)}">${esc(p.email)}</span>`;

    // People this person CAN still draw — pick one to exclude it.
    const others = state.participants
      .filter((q) => q.id !== p.id && !p.exclusions.includes(q.id))
      .sort((a, b) => a.name.localeCompare(b.name));
    const sel = document.createElement("select");
    sel.className = "excl-add";
    sel.title = `People ${p.name} can still draw — pick one to exclude`;
    const ph = document.createElement("option");
    ph.value = "";
    if (!others.length) {
      ph.textContent = "Everyone excluded";
    } else if (others.length === 1) {
      ph.textContent = `Only ${others[0].name} left`;
    } else {
      ph.textContent = "Exclude…";
    }
    ph.disabled = true;
    ph.selected = true;
    sel.appendChild(ph);
    for (const q of others) {
      const opt = document.createElement("option");
      opt.value = q.id;
      if (others.length === 1) {
        // Excluding them would leave p with nobody to draw — the server
        // rejects that state too; just make it unselectable here.
        opt.textContent = `${q.name} (can't exclude everyone)`;
        opt.disabled = true;
      } else {
        opt.textContent = q.name;
      }
      sel.appendChild(opt);
    }
    sel.onchange = () => {
      if (sel.value) saveExclusions(p, [...p.exclusions, sel.value]);
    };
    row.appendChild(sel);

    // Excluded people, popped out to the side — ✕ puts them back.
    const chips = document.createElement("div");
    chips.className = "excl-chips";
    const excluded = p.exclusions
      .map((id) => byId[id])
      .filter(Boolean)
      .sort((a, b) => a.name.localeCompare(b.name));
    if (!excluded.length) {
      chips.innerHTML = `<span class="muted small">none</span>`;
    } else {
      for (const q of excluded) {
        const chip = document.createElement("span");
        chip.className = "excl-chip";
        chip.title = `${p.name} must not give a gift to ${q.name}`;
        chip.textContent = q.name + " ";
        const x = document.createElement("button");
        x.className = "chip-x";
        x.type = "button";
        x.textContent = "✕";
        x.title = `Allow ${q.name} again`;
        x.setAttribute("aria-label", `Remove ${q.name} from ${p.name}'s exclusions`);
        x.onclick = () => saveExclusions(p, p.exclusions.filter((id) => id !== q.id));
        chip.appendChild(x);
        chips.appendChild(chip);
      }
    }
    row.appendChild(chips);

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

// Persist a person's new exclusion list (add/remove a chip or dropdown pick).
async function saveExclusions(p, exclusions) {
  try {
    await api(`/api/participants/${p.id}`, {
      method: "PUT",
      body: JSON.stringify({ name: p.name, email: p.email, exclusions }),
    });
    await refresh();
    flash(`Exclusions updated for ${p.name}`);
  } catch (e) {
    flash(e.message, true);
    await refresh().catch(() => {});
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
  const curSel = $("#set-currency");
  // A pre-dropdown free-text value isn't in the list — keep it as an
  // extra option rather than silently resetting the setting.
  if (s.currency && ![...curSel.options].some((o) => o.value === s.currency)) {
    const opt = document.createElement("option");
    opt.value = s.currency;
    opt.textContent = `${s.currency} (custom)`;
    curSel.prepend(opt);
  }
  curSel.value = s.currency;
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
      // refresh() (not just re-render) so the draw-feasibility check runs
      // again — the reciprocal-pair toggle is a draw constraint.
      await refresh();
      flash("Email settings saved.");
    } catch (e) { flash(e.message, true); }
  };

  // Email preview — uses the current form values (even unsaved) so you can
  // see exactly what would go out.
  $("#preview-email").onclick = async () => {
    try {
      const res = await api("/api/email-preview", {
        method: "POST",
        body: JSON.stringify({
          subject: $("#set-subject").value,
          max_spend: $("#set-spend").value,
          currency: $("#set-currency").value,
          notes: $("#set-notes").value,
        }),
      });
      showPreview(res);
    } catch (e) { flash(e.message, true); }
  };
}

function showPreview(res) {
  $("#preview-subject").textContent = `Subject: ${res.subject}`;
  $("#preview-html").innerHTML = res.html;
  $("#preview-text").textContent = res.text;
  $("#tab-html").classList.add("active");
  $("#tab-text").classList.remove("active");
  $("#preview-html").hidden = false;
  $("#preview-text").hidden = true;
  $("#preview-modal").hidden = false;
}

function closePreview() {
  $("#preview-modal").hidden = true;
}

$("#preview-close").onclick = closePreview;
$("#preview-modal").addEventListener("click", (ev) => {
  if (ev.target === $("#preview-modal")) closePreview();
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && !$("#preview-modal").hidden) closePreview();
});
$("#tab-html").onclick = () => {
  $("#tab-html").classList.add("active");
  $("#tab-text").classList.remove("active");
  $("#preview-html").hidden = false;
  $("#preview-text").hidden = true;
};
$("#tab-text").onclick = () => {
  $("#tab-text").classList.add("active");
  $("#tab-html").classList.remove("active");
  $("#preview-html").hidden = true;
  $("#preview-text").hidden = false;
};

// ---------- draw & send ----------

function renderDraw() {
  const actions = $("#draw-actions");
  const preview = $("#preview");
  const sendSection = $("#send-section");
  const n = state.participants.length;

  // The "hide the draw" toggle is only meaningful once a draw exists.
  const hideWrap = $("#hide-draw-wrap");
  const hideBox = $("#hide-draw");
  const hasDraw = !!state.assignments || !!state.hide_assignments;
  hideWrap.hidden = !hasDraw;
  if (hideBox.checked !== !!state.hide_assignments) hideBox.checked = !!state.hide_assignments;
  hideBox.onchange = async () => {
    try {
      await api("/api/draw/hide", {
        method: "POST",
        body: JSON.stringify({ hide: hideBox.checked }),
      });
      await refresh();
      flash(hideBox.checked ? "Draw hidden — you won't see who draws who." : "Draw visible again.");
    } catch (e) { flash(e.message, true); }
  };

  if (!hasDraw) {
    sendSection.hidden = true;
    preview.innerHTML = "";
    if (n < 2) {
      actions.innerHTML = `<p class="muted">Add at least two participants to draw.</p>`;
      return;
    }
    const blocked = !!(drawCheck && !drawCheck.feasible);
    actions.innerHTML =
      (blocked
        ? `<p class="draw-warn">⚠️ ${esc(drawCheck.reason)}</p>`
        : drawCheck === null
          ? `<span class="muted small">Checking the setup…</span>`
          : "") +
      `<button id="draw-btn" type="button"${blocked ? " disabled title=\"Fix the exclusions problem above first\"" : ""}>🎲 Draw names</button>`;
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
  const entries = Object.entries(state.assignments || {})
    .map(([giver, recipient]) => [byId[giver], byId[recipient]])
    .filter(([g, r]) => g && r)
    .sort((a, b) => a[0].name.localeCompare(b[0].name));

  if (state.hide_assignments) {
    // The organizer chose not to see the draw. The server never sends the
    // mapping, so there's nothing to render — just a note + re-draw.
    actions.innerHTML =
      `<span class="muted">Draw complete — results hidden.</span>` +
      `<button id="redraw" class="ghost" type="button">Re-draw</button>`;
    preview.innerHTML = "";
  } else {
    actions.innerHTML =
      `<span class="muted">Draw complete — you can see below who draws who (keep it secret!).</span>` +
      `<button id="redraw" class="ghost" type="button">Re-draw</button>`;
    preview.innerHTML =
      `<table class="preview"><thead><tr><th>Name</th><th>Gives a gift to</th></tr></thead><tbody>` +
      entries.map(([g, r]) => `<tr><td>${esc(g.name)}</td><td>${esc(r.name)}</td></tr>`).join("") +
      `</tbody></table>`;
  }

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
