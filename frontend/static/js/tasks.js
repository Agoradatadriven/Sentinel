/* =====================================================================
   Task Tracker v0.3 — the service-box board.
   Board = Client rows × Stage columns. A box slides across the stages
   (manual, guarded, logged). Boxes hold single + recurring tasks, an
   approval track, and reconciliation cases. Plus a Personnel view.
   ===================================================================== */
window.pageInit = async (S) => {
  const view = S.view();
  const canManage = S.can("team_lead");        // create/edit boxes, tasks, recon (backend re-checks scope)
  const canAddClient = S.can("account_manager"); // POST /api/clients is AM+
  const canRank = S.can("team_lead");           // personnel ranking is team-lead+

  let [vocab, clients, people] = await Promise.all([
    S.api("/api/vocab"), S.api("/api/clients"), S.api("/api/people"),
  ]);
  const peopleById = Object.fromEntries(people.map((p) => [p.id, p]));
  const STAGES = vocab.box_stages;

  // Stage → pill colour + short label used on chips and column headers.
  const STAGE_META = {
    "In Process": { cls: "red", dot: "var(--danger)" },
    "For Launch": { cls: "amber", dot: "var(--sentinel)" },
    "Launched": { cls: "green", dot: "var(--green)" },
    "Closed": { cls: "grey", dot: "var(--muted)" },
  };
  const stageChip = (st) => `<span class="pill ${(STAGE_META[st] || {}).cls || "grey"}">${S.esc(st)}</span>`;

  // Per-client colour accent — persisted on the client, or a stable fallback from this palette
  // (so a client without a chosen colour still gets a distinct, consistent hue).
  const CLIENT_PALETTE = ["#54B948", "#378add", "#9484FB", "#F2820C", "#17C3B2", "#EC4899", "#F59E0B", "#06B6D4", "#8B5CF6", "#E24B4A"];
  const clientColor = (c) => (c && c.color) || CLIENT_PALETTE[(((c && c.id) || 1) - 1) % CLIENT_PALETTE.length];

  let clientList = clients.slice();
  let tab = "board";
  let filters = { client_id: "", service_line: "", stage: "", team_leader_id: "" };

  render();

  function render() {
    view.innerHTML = `
      <div class="pagehead">
        <div>
          <h2>Task Tracker</h2>
          <div class="lead">Client progress across the pipeline · personnel work, on time.</div>
        </div>
        <div class="row" style="gap:8px">
          ${canAddClient ? `<button class="btn ghost" id="add-client">${S.ICON.plus}Add client</button>` : ""}
          ${canManage ? `<button class="btn primary" id="add-service">${S.ICON.plus}Add service</button>` : ""}
        </div>
      </div>
      <div class="tt-tabs" id="tt-tabs">
        ${["board", "personnel", "billing", "bidbrain"].map((t) =>
          `<button class="tt-tab ${t === tab ? "active" : ""}" data-tab="${t}">${cap(t === "board" ? "Board" : t)}</button>`).join("")}
      </div>
      <div id="tt-body"></div>`;

    S.qsa("#tt-tabs .tt-tab").forEach((b) => (b.onclick = () => { tab = b.dataset.tab; render(); }));
    if (canAddClient) S.qs("#add-client").onclick = () => clientForm();
    if (canManage) S.qs("#add-service").onclick = () => addServiceForm();

    if (tab === "board") boardView();
    else if (tab === "personnel") personnelView();
    else if (tab === "billing") placeholder("wallet", "Billing — separate module",
      "The launched-box card shows only “paid to us” + whether ads are running. Full billing management lives here, away from task tracking. Data source (manual vs. integration) is still to be decided.");
    else placeholder("compass", "Bidbrain — monitoring module",
      "Not a client service — internal monitoring only. Scope, ownership, and UI placement are still to be defined.");
  }

  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  // ---------------- BOARD (matrix) ----------------
  async function boardView() {
    const body = S.qs("#tt-body");
    body.innerHTML = `
      <div class="filters" id="tt-filters">
        <select id="f-client"><option value="">All clients</option>${clientList.map((c) => `<option value="${c.id}" ${filters.client_id == c.id ? "selected" : ""}>${S.esc(c.name)}</option>`).join("")}</select>
        <select id="f-service"><option value="">All services</option>${vocab.service_lines.map((s) => `<option ${filters.service_line === s ? "selected" : ""}>${s}</option>`).join("")}</select>
        <select id="f-stage"><option value="">All stages</option>${STAGES.map((s) => `<option ${filters.stage === s ? "selected" : ""}>${s}</option>`).join("")}</select>
        <select id="f-leader"><option value="">All team leaders</option>${people.map((p) => `<option value="${p.id}" ${filters.team_leader_id == p.id ? "selected" : ""}>${S.esc(p.name)}</option>`).join("")}</select>
        <button class="btn sm ghost" id="f-clear">Clear</button>
      </div>
      <div id="tt-board"><div class="tt-loading">Loading board…</div></div>`;

    const set = (k) => (e) => { filters[k] = e.target.value; loadBoard(); };
    S.qs("#f-client").onchange = set("client_id");
    S.qs("#f-service").onchange = set("service_line");
    S.qs("#f-stage").onchange = set("stage");
    S.qs("#f-leader").onchange = set("team_leader_id");
    S.qs("#f-clear").onclick = () => { filters = { client_id: "", service_line: "", stage: "", team_leader_id: "" }; boardView(); };

    await loadBoard();
  }

  async function loadBoard() {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => { if (v) q.set(k, v); });
    const data = await S.api("/api/boards?" + q);
    clientList = data.clients;
    const el = S.qs("#tt-board");
    if (!el) return;
    if (!data.clients.length) {
      el.innerHTML = `<div class="tt-empty">${S.ICON.board}<p>No clients yet.</p>${canAddClient ? '<button class="btn primary sm" id="empty-add">Add your first client</button>' : ""}</div>`;
      if (canAddClient) S.qs("#empty-add").onclick = () => clientForm();
      return;
    }
    const boxesByClientStage = {};
    data.boxes.forEach((b) => {
      (boxesByClientStage[b.client_id] ||= {});
      (boxesByClientStage[b.client_id][b.stage] ||= []).push(b);
    });

    let html = `<div class="tt-matrix">
      <div class="tt-colhead tt-clienthead">Clients</div>
      ${STAGES.map((s) => `<div class="tt-colhead"><span class="tt-cdot" style="background:${STAGE_META[s].dot}"></span>${S.esc(s)}</div>`).join("")}`;

    data.clients.forEach((c, ri) => {
      const par = ri % 2 === 0 ? "tt-r0" : "tt-r1";   // alternating green / faded-green rows
      const col = clientColor(c);
      html += `<div class="tt-client ${par}" style="--cc:${col}">
        <span class="tt-cname" data-client="${c.id}"><span class="tt-cdotc" style="background:${col}"></span>${S.esc(c.name)}</span>
        <span class="tt-csub">${c.box_count} service${c.box_count === 1 ? "" : "s"}${c.since ? " · since " + S.fmtDate(c.since + "T00:00:00+08:00") : ""}</span>
        ${canManage ? `<button class="tt-addsvc" data-client="${c.id}" title="Add service">${S.ICON.plus}</button>` : ""}
      </div>`;
      STAGES.forEach((st) => {
        const boxes = (boxesByClientStage[c.id] || {})[st] || [];
        html += `<div class="tt-cell ${par}">${boxes.map(boxCard).join("")}</div>`;
      });
    });
    html += `</div>`;
    el.innerHTML = html;

    S.qsa(".tt-cname").forEach((n) => (n.onclick = () => openClient(+n.dataset.client)));
    S.qsa(".tt-addsvc").forEach((n) => (n.onclick = () => addServiceForm(+n.dataset.client)));
    S.qsa(".tt-box").forEach((b) => (b.onclick = (e) => { if (!e.target.closest(".tt-stab")) openBox(+b.dataset.id); }));
    S.qsa(".tt-stab-h").forEach((h) => (h.onclick = (e) => { e.stopPropagation(); h.parentElement.classList.toggle("open"); }));
  }

  function flags(b) {
    const f = [];
    if (b.overdue_count) f.push(`<span class="tt-flag overdue">${b.overdue_count} overdue</span>`);
    if (b.at_risk_count) f.push(`<span class="tt-flag risk">${b.at_risk_count} at risk</span>`);
    if (b.missed_occurrences) f.push(`<span class="tt-flag missed">${b.missed_occurrences} missed</span>`);
    return f.join("");
  }

  function boxCard(b) {
    const tab_ = (label, inner) =>
      `<div class="tt-stab"><div class="tt-stab-h"><span>${label}</span>${S.ICON.chevron || "▾"}</div><div class="tt-stab-c">${inner}</div></div>`;
    const fld = (k, v) => `<div class="tt-field"><span class="k">${k}</span><span class="v">${v}</span></div>`;
    const leader = b.team_leader ? b.team_leader.name : "Unassigned";

    // Top (current-stage) content varies by stage.
    let top = `<div class="tt-svc-meta">Lead: ${S.esc(leader)}</div>`;
    if (b.stage === "Launched") {
      top += fld("Run", b.run_day ? `Day ${b.run_day}${b.run_length_days ? " / " + b.run_length_days : ""}` : "—");
      top += fld("Billing", b.is_paid
        ? `<span style="color:var(--green-d)">Paid${b.ads_running ? " · ads running" : ""}</span>`
        : `<span style="color:var(--danger)">Unpaid</span>`);
    } else if (b.stage === "For Launch") {
      top += fld("Waiting on", "Client start date");
      top += fld("Approved", b.approved_date ? S.fmtDate(b.approved_date + "T00:00:00+08:00") : "—");
    } else if (b.stage === "In Process") {
      top += fld("Started", b.started_date ? S.fmtDate(b.started_date + "T00:00:00+08:00") : "—");
      if (b.revisions_count) top += fld("Approval track", b.revisions_count + " round" + (b.revisions_count === 1 ? "" : "s"));
    } else { // Closed
      top += fld("Ended", b.closed_date ? S.fmtDate(b.closed_date + "T00:00:00+08:00") : "—");
    }
    const fl = flags(b);

    // Collapsible history tabs beneath current stage (pushed down as it progresses).
    let tabs = "";
    const idx = STAGES.indexOf(b.stage);
    if (idx >= 2 && b.launch_date) // Launched or Closed → show Launch-date tab
      tabs += tab_(`Launch date — ${S.fmtDate(b.launch_date + "T00:00:00+08:00")}`,
        fld("Approved", b.approved_date ? S.fmtDate(b.approved_date + "T00:00:00+08:00") : "—") +
        fld("Client confirmed", b.client_confirmed_date ? S.fmtDate(b.client_confirmed_date + "T00:00:00+08:00") : "—"));
    if (idx >= 1) // For Launch onward → show Process tab
      tabs += tab_("Process",
        fld("Started", b.started_date ? S.fmtDate(b.started_date + "T00:00:00+08:00") : "—") +
        fld("Revisions", b.revisions_count + " round" + (b.revisions_count === 1 ? "" : "s")));

    const reconCard = b.open_recon_count
      ? `<div class="tt-recon" data-id="${b.id}">${S.ICON.flame || "!"}<div><strong>Reconciliation</strong> <span class="tt-flag overdue">${b.open_recon_count} open</span></div></div>`
      : "";

    return `<div class="tt-box ${b.stage === "Closed" ? "closed" : ""}" data-id="${b.id}">
      <div class="tt-box-top">
        <div class="tt-box-title">${S.esc(b.service_line)} ${stageChip(b.stage)}</div>
        ${top}
        ${fl ? `<div class="tt-flags">${fl}</div>` : ""}
      </div>
      ${tabs}
    </div>${reconCard}`;
  }

  // ---------------- BOX DETAIL (drawer) ----------------
  async function openBox(id) {
    const b = await S.api("/api/boards/" + id);
    const fld = (k, v) => `<div class="panel-row"><span class="pk">${k}</span><span class="pv">${v}</span></div>`;
    const g = b.guards;

    // Stage control + guard hints.
    const stageOpts = STAGES.map((s) => `<option ${s === b.stage ? "selected" : ""}>${s}</option>`).join("");
    const guardLine = [
      `<span class="tt-guard ${g.can_launch ? "ok" : "no"}">${g.can_launch ? "✓" : "✕"} paid</span>`,
      `<span class="tt-guard ${g.can_close ? "ok" : "no"}">${g.can_close ? "✓" : "✕"} closeable</span>`,
    ].join(" ");

    // Tasks table.
    const tcols = canManage ? 6 : 5;
    const taskRows = b.tasks.length ? b.tasks.map((t) => `
      <tr>
        <td>${S.esc(t.title)}</td>
        <td>${t.assignee ? S.esc(t.assignee.name.split(" ")[0]) : "—"}</td>
        <td>${progBar(t.progress, t.status)}</td>
        <td>${t.due_date ? S.fmtDate(t.due_date + "T00:00:00+08:00") : "—"}</td>
        <td>${taskStatusPill(t)}</td>
        ${canManage ? `<td class="tt-rowact"><button data-task-edit="${t.id}" title="Edit">${S.ICON.gear}</button><button data-task-del="${t.id}" class="del" title="Delete">${S.ICON.x}</button></td>` : ""}
      </tr>`).join("") : `<tr><td colspan="${tcols}" class="muted">No single tasks yet.</td></tr>`;

    // Recurring blocks.
    const recurring = b.recurring.map(recurringBlock).join("") ||
      `<div class="muted" style="font-size:13px">No recurring tasks.</div>`;

    // Approval track (In Process subset).
    const outcomeSel = (r) => `<select data-rev-outcome="${r.id}">${vocab.approval_outcomes.map((o) => `<option ${o === r.approval_outcome ? "selected" : ""}>${o}</option>`).join("")}</select>`;
    const revs = b.revisions.length ? b.revisions.map((r) => `
      <div class="tt-rev-row">
        <div><span class="pk">Revision ${r.round_no}</span> <span class="pv">${S.esc(r.what_changed || "—")}</span>
          <div class="tt-recon-meta">ball: ${S.esc(r.ball_with)}</div></div>
        <div class="tt-rev-act">${canManage ? outcomeSel(r) + `<button data-rev-del="${r.id}" class="tt-x del" title="Delete">${S.ICON.x}</button>` : `<em>${S.esc(r.approval_outcome)}</em>`}</div>
      </div>`).join("")
      : `<div class="muted" style="font-size:13px">No revision rounds logged.</div>`;

    // Reconciliation.
    const recons = b.reconciliations.length ? b.reconciliations.map((r) => `
      <div class="tt-recon-card ${r.is_open ? "open" : "resolved"}">
        <div class="tt-recon-head"><strong>${S.esc(r.trigger_type)}</strong><span class="pill ${r.is_open ? "red" : "green"}">${S.esc(r.status)}</span></div>
        ${r.description ? `<div class="sub">${S.esc(r.description)}</div>` : ""}
        <div class="tt-recon-meta">Owner: ${r.owner ? S.esc(r.owner.name) : "—"} · Opened ${S.fmtDate(r.opened_at)}${r.resolution ? " · " + S.esc(r.resolution) : ""}</div>
        ${canManage ? `<div class="row" style="gap:6px;margin-top:6px">
          ${r.is_open ? `<button class="btn sm ghost" data-recon-resolve="${r.id}">Mark resolved</button>` : ""}
          <button class="btn sm ghost" data-recon-edit="${r.id}">Edit</button>
          <button class="btn sm ghost danger-text" data-recon-del="${r.id}">Delete</button>
        </div>` : ""}
      </div>`).join("") : `<div class="muted" style="font-size:13px">No reconciliation cases.</div>`;

    // Stage history.
    const hist = b.transitions.map((t) => `
      <div class="tt-hist-row"><span class="tt-hist-dot" style="background:${(STAGE_META[t.to_stage] || {}).dot || "var(--muted)"}"></span>
        <strong>${S.esc(t.to_stage)}</strong>${t.is_backward ? ' <span class="tt-flag overdue">back</span>' : ""}
        · ${S.fmtDate(t.created_at)} · ${t.moved_by ? S.esc(t.moved_by.name) : "System"}
        ${t.reason ? `<div class="sub">“${S.esc(t.reason)}”</div>` : ""}</div>`).join("");

    const body = `
      <div class="tt-stagebar">
        ${stageChip(b.stage)}
        ${canManage ? `<select id="d-stage">${stageOpts}</select>` : ""}
        <span class="tt-guards">${guardLine}</span>
      </div>
      ${canManage ? `<div class="row" style="gap:14px;margin:-4px 0 14px;align-items:center;flex-wrap:wrap">
        <label class="tt-check"><input type="checkbox" id="d-paid" ${b.is_paid ? "checked" : ""}> Paid</label>
        <label class="tt-check"><input type="checkbox" id="d-ads" ${b.ads_running ? "checked" : ""}> Ads running</label>
        <span style="margin-left:auto"></span>
        <button class="btn sm ghost" id="d-edit-box">${S.ICON.gear}Edit box</button>
        <button class="btn sm ghost danger-text" id="d-del-box">Delete box</button>
      </div>` : ""}

      <div class="panel-section">
        <h3>Service</h3>
        ${fld("Team leader (receiver)", b.team_leader ? S.esc(b.team_leader.name) : "—")}
        ${fld("Run", b.run_day ? `Day ${b.run_day}${b.run_length_days ? " / " + b.run_length_days : ""}` : "—")}
        ${fld("Started", b.started_date ? S.fmtDateFull(b.started_date + "T00:00:00+08:00") : "—")}
      </div>

      <div class="panel-section">
        <div class="tt-sec-head"><h3>Tasks</h3>${canManage ? `<button class="btn sm ghost" id="d-add-task">${S.ICON.plus}Add task</button>` : ""}</div>
        <table class="tt-tasktable"><thead><tr><th>Task</th><th>Who</th><th>Progress</th><th>Target</th><th>Status</th>${canManage ? "<th></th>" : ""}</tr></thead>
          <tbody>${taskRows}</tbody></table>
      </div>

      <div class="panel-section">
        <div class="tt-sec-head"><h3>Recurring</h3>${canManage ? `<button class="btn sm ghost" id="d-add-rec">${S.ICON.plus}Add recurring</button>` : ""}</div>
        ${recurring}
      </div>

      <div class="panel-section">
        <div class="tt-sec-head"><h3>Approval track <span class="muted" style="font-weight:400;text-transform:none">· revisions &amp; approvals</span></h3>${canManage ? `<button class="btn sm ghost" id="d-add-rev">${S.ICON.plus}Add round</button>` : ""}</div>
        <div class="tt-subset">${revs}</div>
      </div>

      <div class="panel-section">
        <div class="tt-sec-head"><h3>Reconciliation</h3>${canManage && b.stage === "Launched" ? `<button class="btn sm ghost" id="d-add-recon">${S.ICON.plus}Open case</button>` : ""}</div>
        ${recons}
      </div>

      <div class="panel-section"><h3>Stage history</h3><div class="tt-hist">${hist}</div></div>`;

    const m = S.modal({ title: `${b.service_line} — ${b.client_name}`, body, wide: true });

    // Stage move (with guard errors surfaced + backward reason prompt).
    const sel = S.qs("#d-stage");
    if (sel) sel.onchange = async () => {
      const target = sel.value;
      let reason = null;
      if (STAGES.indexOf(target) < STAGES.indexOf(b.stage)) {
        reason = prompt(`Moving “${b.service_line}” back to ${target}. Reason? (required)`);
        if (!reason) { sel.value = b.stage; return; }
      }
      try {
        await S.api(`/api/boards/${b.id}/stage`, { method: "POST", body: { stage: target, reason } });
        S.toast("Moved to " + target, "ok"); m.close(); loadBoard();
      } catch (e) { S.toast(e.detail, "err"); sel.value = b.stage; }
    };
    const patchBox = async (patch) => {
      try { await S.api(`/api/boards/${b.id}`, { method: "PATCH", body: patch }); S.toast("Saved", "ok"); }
      catch (e) { S.toast(e.detail, "err"); }
    };
    if (S.qs("#d-paid")) S.qs("#d-paid").onchange = (e) => patchBox({ is_paid: e.target.checked });
    if (S.qs("#d-ads")) S.qs("#d-ads").onchange = (e) => patchBox({ ads_running: e.target.checked });

    if (S.qs("#d-add-task")) S.qs("#d-add-task").onclick = () => addTaskForm(b, m);
    if (S.qs("#d-add-rec")) S.qs("#d-add-rec").onclick = () => addRecurringForm(b, m);
    if (S.qs("#d-add-rev")) S.qs("#d-add-rev").onclick = () => addRevisionForm(b, m);
    if (S.qs("#d-add-recon")) S.qs("#d-add-recon").onclick = () => addReconForm(b, m);

    // Box edit / delete.
    if (S.qs("#d-edit-box")) S.qs("#d-edit-box").onclick = () => editBoxForm(b, m);
    if (S.qs("#d-del-box")) S.qs("#d-del-box").onclick = async () => {
      if (!confirm(`Delete the ${b.service_line} box for ${b.client_name}? Its recurring tasks, reconciliation and revision history are removed; single tasks are detached (kept). This can't be undone.`)) return;
      try { await S.api(`/api/boards/${b.id}`, { method: "DELETE" }); S.toast("Service box deleted", "ok"); m.close(); loadBoard(); }
      catch (e) { S.toast(e.detail, "err"); }
    };
    // Task edit / delete.
    S.qsa("[data-task-edit]").forEach((btn) => (btn.onclick = () => {
      const t = b.tasks.find((x) => x.id === +btn.dataset.taskEdit); if (t) editTaskForm(t, b, m);
    }));
    S.qsa("[data-task-del]").forEach((btn) => (btn.onclick = async () => {
      const t = b.tasks.find((x) => x.id === +btn.dataset.taskDel);
      if (!confirm(`Delete task "${t ? t.title : ""}"? This can't be undone.`)) return;
      try { await S.api(`/api/tasks/${btn.dataset.taskDel}`, { method: "DELETE" }); S.toast("Task deleted", "ok"); m.close(); openBox(id); }
      catch (e) { S.toast(e.detail, "err"); }
    }));
    // Recurring edit / delete.
    S.qsa("[data-rec-edit]").forEach((btn) => (btn.onclick = () => {
      const r = b.recurring.find((x) => x.id === +btn.dataset.recEdit); if (r) editRecurringForm(r, b, m);
    }));
    S.qsa("[data-rec-del]").forEach((btn) => (btn.onclick = async () => {
      if (!confirm("Delete this recurring task and its history? This can't be undone.")) return;
      try { await S.api(`/api/boards/recurring/${btn.dataset.recDel}`, { method: "DELETE" }); S.toast("Recurring task deleted", "ok"); m.close(); openBox(id); }
      catch (e) { S.toast(e.detail, "err"); }
    }));
    // Revision outcome / delete.
    S.qsa("[data-rev-outcome]").forEach((sel2) => (sel2.onchange = async () => {
      try { await S.api(`/api/boards/revision/${sel2.dataset.revOutcome}`, { method: "PATCH", body: { approval_outcome: sel2.value } }); S.toast("Outcome updated", "ok"); }
      catch (e) { S.toast(e.detail, "err"); }
    }));
    S.qsa("[data-rev-del]").forEach((btn) => (btn.onclick = async () => {
      if (!confirm("Delete this revision round?")) return;
      try { await S.api(`/api/boards/revision/${btn.dataset.revDel}`, { method: "DELETE" }); S.toast("Revision deleted", "ok"); m.close(); openBox(id); }
      catch (e) { S.toast(e.detail, "err"); }
    }));
    // Reconciliation edit / delete.
    S.qsa("[data-recon-edit]").forEach((btn) => (btn.onclick = () => {
      const r = b.reconciliations.find((x) => x.id === +btn.dataset.reconEdit); if (r) editReconForm(r, b, m);
    }));
    S.qsa("[data-recon-del]").forEach((btn) => (btn.onclick = async () => {
      if (!confirm("Delete this reconciliation case?")) return;
      try { await S.api(`/api/boards/reconciliation/${btn.dataset.reconDel}`, { method: "DELETE" }); S.toast("Reconciliation deleted", "ok"); m.close(); openBox(id); }
      catch (e) { S.toast(e.detail, "err"); }
    }));

    // Due-now check-offs.
    S.qsa("[data-occ]").forEach((cb) => (cb.onchange = async () => {
      const tid = cb.dataset.occ, d = cb.dataset.date;
      try {
        await S.api(`/api/boards/recurring/${tid}/occurrence`, { method: "POST", body: { occurrence_date: d, done: cb.checked } });
        S.toast(cb.checked ? "Checked off" : "Unchecked", "ok"); m.close(); openBox(id);
      } catch (e) { S.toast(e.detail, "err"); cb.checked = !cb.checked; }
    }));
    // Resolve reconciliation.
    S.qsa("[data-recon-resolve]").forEach((btn) => (btn.onclick = async () => {
      try {
        await S.api(`/api/boards/reconciliation/${btn.dataset.reconResolve}`, { method: "PATCH", body: { status: "Resolved" } });
        S.toast("Reconciliation resolved", "ok"); m.close(); openBox(id); loadBoard();
      } catch (e) { S.toast(e.detail, "err"); }
    }));
  }

  function progBar(p, status) {
    p = p || 0;
    const col = status === "Completed" ? "var(--green)" : p < 34 ? "var(--danger)" : p < 67 ? "var(--sentinel)" : "var(--green)";
    return `<span class="tt-prog"><i style="width:${p}%;background:${col}"></i></span>${p}%`;
  }
  function taskStatusPill(t) {
    if (t.status === "Completed") return `<span class="tt-flag done">${t.on_time === false ? "Late" : "Done"}</span>`;
    if (t.due_date && t.due_date < new Date().toISOString().slice(0, 10)) return `<span class="tt-flag overdue">Overdue</span>`;
    return `<span class="pill grey">${S.esc(t.status)}</span>`;
  }

  function recurringBlock(r) {
    const cad = { Daily: "blue", Weekly: "amber", Monthly: "violet" }[r.cadence] || "grey";
    const strip = r.strip.map((s) => `<span class="tt-adh-dot ${s.state}" title="${s.date} · ${s.state}"></span>`).join("");
    const due = r.due ? `
      <label class="tt-due"><input type="checkbox" data-occ="${r.id}" data-date="${r.due.occurrence_date}" ${r.due.done ? "checked" : ""}>
        ${S.esc(r.title)} — ${S.fmtDate(r.due.occurrence_date + "T00:00:00+08:00")}${r.due.done ? " ✓" : ""}</label>` : "";
    return `<div class="tt-rec">
      <div class="tt-rec-head"><strong>${S.esc(r.title)}${r.active ? "" : ' <span class="tt-flag missed">paused</span>'}</strong>
        <span class="row" style="gap:6px;align-items:center"><span class="pill ${cad}">${r.cadence}</span>
        ${canManage ? `<button data-rec-edit="${r.id}" class="tt-x" title="Edit">${S.ICON.gear}</button><button data-rec-del="${r.id}" class="tt-x del" title="Delete">${S.ICON.x}</button>` : ""}</span></div>
      <div class="tt-rec-meta">${r.assignee ? S.esc(r.assignee.name) : "Unassigned"} · ${r.time_span_hours}h/occ</div>
      <div class="tt-adh-strip">${strip}</div>
      <div class="tt-adh-key"><span><span class="tt-adh-dot done"></span>done</span><span><span class="tt-adh-dot missed"></span>missed</span><span><span class="tt-adh-dot today"></span>today</span><span><span class="tt-adh-dot upcoming"></span>upcoming</span></div>
      ${due}
      <div class="tt-rec-meta">Adherence: ${r.adherence_pct}% (${r.done_total} done · ${r.missed_total} missed)</div>
    </div>`;
  }

  // ---------------- CLIENT PROFILE (drawer) ----------------
  async function openClient(cid) {
    const data = await S.api("/api/boards?client_id=" + cid);
    const c = data.clients.find((x) => x.id === cid) || {};
    const boxes = data.boxes;
    const row = (k, v) => `<div class="panel-row"><span class="pk">${k}</span><span class="pv">${v}</span></div>`;
    const svc = boxes.map((b) => `<div class="panel-row"><span class="pk">${S.esc(b.service_line)}</span><span class="pv">${stageChip(b.stage)} ${b.team_leader ? '<span class="muted">· ' + S.esc(b.team_leader.name.split(" ")[0]) + "</span>" : ""}</span></div>`).join("")
      || `<div class="muted">No services yet.</div>`;
    const col = clientColor(c);
    const body = `
      ${canAddClient ? `<div class="row" style="gap:8px;margin-bottom:14px">
        <button class="btn sm ghost" id="cp-edit">${S.ICON.gear}Edit</button>
        <button class="btn sm ghost danger-text" id="cp-del">${S.ICON.x}Delete</button>
      </div>` : ""}
      <div class="panel-section"><h3>Account</h3>
        ${row("Colour", `<span class="tt-cdotc" style="background:${col};vertical-align:middle"></span>`)}
        ${row("Name", S.esc(c.name || "—"))}
        ${row("Contact", c.contact_email ? `<span style="color:var(--violet-d)">${S.esc(c.contact_email)}</span>` : "—")}
        ${row("Atrium link", c.atrium_client_id ? S.esc(c.atrium_client_id) : "—")}
        ${row("Since", c.since ? S.fmtDateFull(c.since + "T00:00:00+08:00") : "—")}
      </div>
      <div class="panel-section"><h3>Services (${boxes.length})</h3>${svc}</div>
      <div class="panel-section"><h3>Roll-up</h3>
        ${row("Open tasks", boxes.reduce((n, b) => n + b.task_open, 0))}
        ${row("Overdue", boxes.reduce((n, b) => n + b.overdue_count, 0))}
        ${row("Open reconciliations", boxes.reduce((n, b) => n + b.open_recon_count, 0))}
      </div>
      ${canManage ? `<button class="btn primary block" id="cp-add">${S.ICON.plus}Add a service for ${S.esc(c.name)}</button>` : ""}`;
    const m = S.modal({ title: c.name || "Client", body });
    if (S.qs("#cp-add")) S.qs("#cp-add").onclick = () => { m.close(); addServiceForm(cid); };
    if (S.qs("#cp-edit")) S.qs("#cp-edit").onclick = () => { m.close(); clientForm(c); };
    if (S.qs("#cp-del")) S.qs("#cp-del").onclick = async () => {
      if (!confirm(`Delete "${c.name}"? This also removes its ${boxes.length} service box(es) and detaches their tasks. This can't be undone.`)) return;
      try {
        await S.api("/api/clients/" + cid, { method: "DELETE" });
        clients = clients.filter((x) => x.id !== cid); clientList = clients.slice();
        S.toast("Client deleted", "ok"); m.close(); render();
      } catch (e) { S.toast(e.detail || "Couldn't delete client", "err"); }
    };
  }

  // ---------------- PERSONNEL ----------------
  async function personnelView() {
    const body = S.qs("#tt-body");
    body.innerHTML = `<div class="tt-loading">Loading…</div>`;
    const queue = await S.api("/api/boards/perf/queue");
    const ranking = canRank ? await S.api("/api/boards/perf/ranking") : null;

    const dueItems = [
      ...queue.due_recurring.map((d) => `<label class="tt-due"><input type="checkbox" data-occ="${d.template_id}" data-date="${d.occurrence_date}"> ${S.esc(d.title)} <span class="muted">· ${S.esc(d.client_name || "")} · ${d.cadence}</span></label>`),
      ...queue.overdue_tasks.map((t) => `<div class="tt-due"><span class="tt-flag overdue">overdue</span> ${S.esc(t.title)} <span class="muted">· ${t.due_date ? S.fmtDate(t.due_date + "T00:00:00+08:00") : ""}</span></div>`),
    ].join("") || `<div class="muted">Nothing due right now 🎉</div>`;

    const me = queue.me;
    let html = `
      <div class="tt-perf-card">
        <div class="tt-sec-head"><h3>My due now</h3><span class="muted">${queue.open_tasks.length} open · ${queue.overdue_tasks.length} overdue</span></div>
        <div class="tt-duelist">${dueItems}</div>
      </div>`;

    if (ranking) {
      html += `<h3 class="tt-rank-title">Personnel ranking</h3>
        <div class="tt-ranklist">${ranking.map(rankCard).join("")}</div>
        <div class="tt-note">Ranked on objective, dated signals — on-time rate &amp; adherence. Hours are shown but not ranked (self-reported).</div>`;
    } else {
      html += `<div class="tt-perf-card">${metricRow(me)}</div>`;
    }
    body.innerHTML = html;

    S.qsa("[data-occ]").forEach((cb) => (cb.onchange = async () => {
      try {
        await S.api(`/api/boards/recurring/${cb.dataset.occ}/occurrence`, { method: "POST", body: { occurrence_date: cb.dataset.date, done: cb.checked } });
        S.toast(cb.checked ? "Checked off" : "Unchecked", "ok"); personnelView();
      } catch (e) { S.toast(e.detail, "err"); cb.checked = !cb.checked; }
    }));
  }

  const num = (v) => (v == null ? "—" : v);
  function metricRow(r) {
    const M = (val, lbl, col) => `<div class="tt-metric"><div class="tt-mv" ${col ? `style="color:${col}"` : ""}>${val}</div><div class="tt-ml">${lbl}</div></div>`;
    return `<div class="tt-metrics">
      ${M(r.on_time_rate == null ? "—" : r.on_time_rate + "%", "On-time", r.on_time_rate >= 80 ? "var(--green-d)" : r.on_time_rate == null ? "" : "var(--sentinel)")}
      ${M(r.adherence_pct == null ? "—" : r.adherence_pct + "%", "Adherence", r.adherence_pct >= 80 ? "var(--green-d)" : r.adherence_pct == null ? "" : "var(--sentinel)")}
      ${M(r.open_count, "Open")}
      ${M(r.overdue_count, "Overdue", r.overdue_count ? "var(--danger)" : "")}
    </div>
    <div class="tt-hours">${S.ICON.clock} Hours (informational): avg ${num(r.avg_actual_hours)}h actual vs ${num(r.avg_allotted_hours)}h allotted · ${r.finished_count} finished</div>`;
  }
  function rankCard(r) {
    return `<div class="tt-perf-card">
      <div class="tt-perf-head">
        <div class="tt-rankno">${r.rank || "—"}</div>
        ${S.avatar(r.user)}
        <div><div class="tt-perf-name">${S.esc(r.user.name)}</div><div class="tt-perf-role">${S.esc(r.user.role_label || r.user.role)}</div></div>
        <div class="tt-score" title="Objective score">${r.score == null ? "—" : r.score}</div>
      </div>
      ${metricRow(r)}
    </div>`;
  }

  // ---------------- FORMS ----------------
  function clientForm(existing) {
    const e = existing || {};
    const isEdit = !!(e && e.id);
    let selected = clientColor(isEdit ? e : { id: clients.length + 1 });
    const swatches = CLIENT_PALETTE.map((hex) =>
      `<button type="button" class="tt-sw ${hex.toLowerCase() === selected.toLowerCase() ? "sel" : ""}" data-hex="${hex}" style="background:${hex}"></button>`).join("");
    const m = S.modal({
      title: isEdit ? "Edit client" : "Add client",
      body: `<label class="field"><span>Name</span><input id="c-name" value="${S.esc(e.name || "")}" placeholder="Client name"></label>
        <label class="field"><span>Contact email</span><input id="c-email" value="${S.esc(e.contact_email || "")}" placeholder="ops@client.com"></label>
        <label class="field"><span>Atrium client key (optional)</span><input id="c-atrium" value="${S.esc(e.atrium_client_id || "")}" placeholder="bridges to Atrium"></label>
        <label class="field"><span>Board colour</span>
          <div class="tt-swatches" id="c-sw">${swatches}
            <label class="tt-sw-custom" title="Custom colour"><input type="color" id="c-color" value="${selected}"></label>
          </div>
        </label>`,
      footer: `<button class="btn ghost" id="c-cancel">Cancel</button><button class="btn primary" id="c-save">${isEdit ? "Save changes" : "Add client"}</button>`,
    });
    const paint = () => S.qsa("#c-sw .tt-sw").forEach((b) => b.classList.toggle("sel", b.dataset.hex.toLowerCase() === selected.toLowerCase()));
    S.qsa("#c-sw .tt-sw").forEach((b) => (b.onclick = () => { selected = b.dataset.hex; S.qs("#c-color").value = selected; paint(); }));
    S.qs("#c-color").oninput = (ev) => { selected = ev.target.value; paint(); };
    S.qs("#c-cancel").onclick = m.close;
    S.qs("#c-save").onclick = async () => {
      const name = S.qs("#c-name").value.trim();
      if (!name) return S.toast("Name is required", "err");
      const body = { name, contact_email: S.qs("#c-email").value || null, atrium_client_id: S.qs("#c-atrium").value || null, color: selected };
      try {
        if (isEdit) {
          const c = await S.api("/api/clients/" + e.id, { method: "PATCH", body });
          clients = clients.map((x) => (x.id === c.id ? c : x));
        } else {
          const c = await S.api("/api/clients", { method: "POST", body });
          clients.push(c);
        }
        clientList = clients.slice();
        S.toast(isEdit ? "Client updated" : "Client added", "ok"); m.close(); render();
      } catch (e) { S.toast(e.detail || "Couldn't save client", "err"); }
    };
  }

  function addServiceForm(preClient) {
    const takenNote = "";
    const m = S.modal({
      title: "Add service box",
      body: `<label class="field"><span>Client</span><select id="s-client">${clientList.map((c) => `<option value="${c.id}" ${c.id === preClient ? "selected" : ""}>${S.esc(c.name)}</option>`).join("")}</select></label>
        <label class="field"><span>Service line</span><select id="s-line">${vocab.service_lines.map((s) => `<option>${s}</option>`).join("")}</select></label>
        <label class="field"><span>Team leader (receiver)</span><select id="s-leader"><option value="">—</option>${people.map((p) => `<option value="${p.id}">${S.esc(p.name)}</option>`).join("")}</select></label>
        <label class="field"><span>Length of run (days, optional)</span><input type="number" id="s-run" placeholder="e.g. 180"></label>
        ${takenNote}`,
      footer: `<button class="btn ghost" id="s-cancel">Cancel</button><button class="btn primary" id="s-save">Create box</button>`,
    });
    S.qs("#s-cancel").onclick = m.close;
    S.qs("#s-save").onclick = async () => {
      const body = {
        client_id: +S.qs("#s-client").value, service_line: S.qs("#s-line").value,
        team_leader_id: S.qs("#s-leader").value ? +S.qs("#s-leader").value : null,
        run_length_days: S.qs("#s-run").value ? +S.qs("#s-run").value : null,
      };
      try { await S.api("/api/boards", { method: "POST", body }); S.toast("Service box created", "ok"); m.close(); tab = "board"; render(); }
      catch (e) { S.toast(e.detail, "err"); }
    };
  }

  function addTaskForm(box, parent) {
    const m = S.modal({
      title: "Add task",
      body: `<label class="field"><span>Task</span><input id="t-title" placeholder="What needs doing?"></label>
        <label class="field"><span>Assignee</span><select id="t-assignee"><option value="">Unassigned</option>${people.map((p) => `<option value="${p.id}">${S.esc(p.name)}</option>`).join("")}</select></label>
        <div class="row" style="gap:10px">
          <label class="field" style="flex:1"><span>Target date</span><input type="date" id="t-due"></label>
          <label class="field" style="flex:1"><span>Time span (h)</span><input type="number" step="0.5" id="t-span" placeholder="4"></label>
        </div>
        <div class="sub" style="margin-top:-4px">Receiver: <strong>${box.team_leader ? S.esc(box.team_leader.name) : "the team leader"}</strong> (auto)</div>`,
      footer: `<button class="btn ghost" id="t-cancel">Cancel</button><button class="btn primary" id="t-save">Add task</button>`,
    });
    S.qs("#t-cancel").onclick = m.close;
    S.qs("#t-save").onclick = async () => {
      const title = S.qs("#t-title").value.trim();
      if (!title) return S.toast("Task name required", "err");
      const body = {
        title, service_box_id: box.id, client_id: box.client_id,
        assigned_to_id: S.qs("#t-assignee").value ? +S.qs("#t-assignee").value : null,
        due_date: S.qs("#t-due").value || null, status: "In Progress",
        time_span_hours: S.qs("#t-span").value ? +S.qs("#t-span").value : null,
      };
      try { await S.api("/api/tasks", { method: "POST", body }); S.toast("Task added", "ok"); m.close(); parent.close(); openBox(box.id); }
      catch (e) { S.toast(e.detail, "err"); }
    };
  }

  function addRecurringForm(box, parent) {
    const today = new Date().toISOString().slice(0, 10);
    const m = S.modal({
      title: "Add recurring task",
      body: `<label class="field"><span>Task</span><input id="r-title" placeholder="e.g. Daily ad monitoring"></label>
        <div class="row" style="gap:10px">
          <label class="field" style="flex:1"><span>Cadence</span><select id="r-cad">${vocab.cadences.map((c) => `<option>${c}</option>`).join("")}</select></label>
          <label class="field" style="flex:1"><span>Time span (h/occ)</span><input type="number" step="0.5" id="r-span" value="1"></label>
        </div>
        <label class="field"><span>Assignee</span><select id="r-assignee"><option value="">Unassigned</option>${people.map((p) => `<option value="${p.id}">${S.esc(p.name)}</option>`).join("")}</select></label>
        <div class="row" style="gap:10px">
          <label class="field" style="flex:1"><span>Start</span><input type="date" id="r-start" value="${today}"></label>
          <label class="field" style="flex:1"><span>End (optional)</span><input type="date" id="r-end"></label>
        </div>`,
      footer: `<button class="btn ghost" id="r-cancel">Cancel</button><button class="btn primary" id="r-save">Add recurring</button>`,
    });
    S.qs("#r-cancel").onclick = m.close;
    S.qs("#r-save").onclick = async () => {
      const title = S.qs("#r-title").value.trim();
      if (!title) return S.toast("Task name required", "err");
      const body = {
        title, cadence: S.qs("#r-cad").value, time_span_hours: +S.qs("#r-span").value || 1,
        assignee_id: S.qs("#r-assignee").value ? +S.qs("#r-assignee").value : null,
        start_date: S.qs("#r-start").value, end_date: S.qs("#r-end").value || null,
      };
      try { await S.api(`/api/boards/${box.id}/recurring`, { method: "POST", body }); S.toast("Recurring task added", "ok"); m.close(); parent.close(); openBox(box.id); }
      catch (e) { S.toast(e.detail, "err"); }
    };
  }

  function addRevisionForm(box, parent) {
    const m = S.modal({
      title: "Add revision round",
      body: `<label class="field"><span>What changed</span><textarea id="v-what" placeholder="Describe the revision"></textarea></label>
        <label class="field"><span>Ball is with</span><select id="v-ball">${vocab.ball_with.map((b) => `<option value="${b}">${b === "us" ? "Us" : "Client"}</option>`).join("")}</select></label>`,
      footer: `<button class="btn ghost" id="v-cancel">Cancel</button><button class="btn primary" id="v-save">Add round</button>`,
    });
    S.qs("#v-cancel").onclick = m.close;
    S.qs("#v-save").onclick = async () => {
      try { await S.api(`/api/boards/${box.id}/revision`, { method: "POST", body: { what_changed: S.qs("#v-what").value || null, ball_with: S.qs("#v-ball").value } }); S.toast("Round added", "ok"); m.close(); parent.close(); openBox(box.id); }
      catch (e) { S.toast(e.detail, "err"); }
    };
  }

  function addReconForm(box, parent) {
    const m = S.modal({
      title: "Open reconciliation case",
      body: `<label class="field"><span>Trigger</span><select id="rc-trigger">${vocab.recon_triggers.map((t) => `<option>${t}</option>`).join("")}</select></label>
        <label class="field"><span>Description</span><textarea id="rc-desc" placeholder="What's the discrepancy?"></textarea></label>
        <label class="field"><span>Owner</span><select id="rc-owner"><option value="">Team leader</option>${people.map((p) => `<option value="${p.id}">${S.esc(p.name)}</option>`).join("")}</select></label>`,
      footer: `<button class="btn ghost" id="rc-cancel">Cancel</button><button class="btn primary" id="rc-save">Open case</button>`,
    });
    S.qs("#rc-cancel").onclick = m.close;
    S.qs("#rc-save").onclick = async () => {
      const body = { trigger_type: S.qs("#rc-trigger").value, description: S.qs("#rc-desc").value || null, owner_id: S.qs("#rc-owner").value ? +S.qs("#rc-owner").value : null };
      try { await S.api(`/api/boards/${box.id}/reconciliation`, { method: "POST", body }); S.toast("Reconciliation opened", "ok"); m.close(); parent.close(); openBox(box.id); loadBoard(); }
      catch (e) { S.toast(e.detail, "err"); }
    };
  }

  function editBoxForm(box, parent) {
    const m = S.modal({
      title: `Edit ${box.service_line} — ${box.client_name}`,
      body: `<label class="field"><span>Team leader (receiver)</span><select id="eb-leader"><option value="">—</option>${people.map((p) => `<option value="${p.id}" ${box.team_leader_id === p.id ? "selected" : ""}>${S.esc(p.name)}</option>`).join("")}</select></label>
        <label class="field"><span>Length of run (days)</span><input type="number" id="eb-run" value="${box.run_length_days || ""}"></label>
        <label class="field"><span>Notes</span><textarea id="eb-notes">${S.esc(box.notes || "")}</textarea></label>`,
      footer: `<button class="btn ghost" id="eb-cancel">Cancel</button><button class="btn primary" id="eb-save">Save</button>`,
    });
    S.qs("#eb-cancel").onclick = m.close;
    S.qs("#eb-save").onclick = async () => {
      const body = { team_leader_id: S.qs("#eb-leader").value ? +S.qs("#eb-leader").value : null, run_length_days: S.qs("#eb-run").value ? +S.qs("#eb-run").value : null, notes: S.qs("#eb-notes").value || null };
      try { await S.api(`/api/boards/${box.id}`, { method: "PATCH", body }); S.toast("Box updated", "ok"); m.close(); parent.close(); openBox(box.id); loadBoard(); }
      catch (e) { S.toast(e.detail, "err"); }
    };
  }

  function editTaskForm(t, box, parent) {
    const m = S.modal({
      title: "Edit task",
      body: `<label class="field"><span>Task</span><input id="et-title" value="${S.esc(t.title)}"></label>
        <label class="field"><span>Assignee</span><select id="et-assignee"><option value="">Unassigned</option>${people.map((p) => `<option value="${p.id}" ${t.assigned_to_id === p.id ? "selected" : ""}>${S.esc(p.name)}</option>`).join("")}</select></label>
        <div class="row" style="gap:10px">
          <label class="field" style="flex:1"><span>Target date</span><input type="date" id="et-due" value="${t.due_date || ""}"></label>
          <label class="field" style="flex:1"><span>Time span (h)</span><input type="number" step="0.5" id="et-span" value="${t.time_span_hours || ""}"></label>
        </div>
        <div class="row" style="gap:10px">
          <label class="field" style="flex:1"><span>Progress %</span><input type="number" min="0" max="100" id="et-prog" value="${t.progress || 0}"></label>
          <label class="field" style="flex:1"><span>Status</span><select id="et-status">${vocab.task_statuses.map((s) => `<option ${s === t.status ? "selected" : ""}>${s}</option>`).join("")}</select></label>
        </div>`,
      footer: `<button class="btn ghost" id="et-cancel">Cancel</button><button class="btn primary" id="et-save">Save</button>`,
    });
    S.qs("#et-cancel").onclick = m.close;
    S.qs("#et-save").onclick = async () => {
      const title = S.qs("#et-title").value.trim();
      if (!title) return S.toast("Task name required", "err");
      const newStatus = S.qs("#et-status").value;
      const body = { title, assigned_to_id: S.qs("#et-assignee").value ? +S.qs("#et-assignee").value : null, due_date: S.qs("#et-due").value || null, time_span_hours: S.qs("#et-span").value ? +S.qs("#et-span").value : null, progress: +S.qs("#et-prog").value || 0 };
      try {
        await S.api(`/api/tasks/${t.id}`, { method: "PATCH", body });
        if (newStatus !== t.status) await S.api(`/api/tasks/${t.id}/status`, { method: "PATCH", body: { status: newStatus } });
        S.toast("Task updated", "ok"); m.close(); parent.close(); openBox(box.id);
      } catch (e) { S.toast(e.detail, "err"); }
    };
  }

  function editRecurringForm(r, box, parent) {
    const m = S.modal({
      title: "Edit recurring task",
      body: `<label class="field"><span>Task</span><input id="er-title" value="${S.esc(r.title)}"></label>
        <div class="row" style="gap:10px">
          <label class="field" style="flex:1"><span>Cadence</span><select id="er-cad">${vocab.cadences.map((c) => `<option ${c === r.cadence ? "selected" : ""}>${c}</option>`).join("")}</select></label>
          <label class="field" style="flex:1"><span>Time span (h/occ)</span><input type="number" step="0.5" id="er-span" value="${r.time_span_hours}"></label>
        </div>
        <label class="field"><span>Assignee</span><select id="er-assignee"><option value="">Unassigned</option>${people.map((p) => `<option value="${p.id}" ${r.assignee_id === p.id ? "selected" : ""}>${S.esc(p.name)}</option>`).join("")}</select></label>
        <label class="field"><span>End date (optional)</span><input type="date" id="er-end" value="${r.end_date || ""}"></label>
        <label class="tt-check"><input type="checkbox" id="er-active" ${r.active ? "checked" : ""}> Active (uncheck to pause)</label>`,
      footer: `<button class="btn ghost" id="er-cancel">Cancel</button><button class="btn primary" id="er-save">Save</button>`,
    });
    S.qs("#er-cancel").onclick = m.close;
    S.qs("#er-save").onclick = async () => {
      const body = { title: S.qs("#er-title").value.trim(), cadence: S.qs("#er-cad").value, time_span_hours: +S.qs("#er-span").value || 1, assignee_id: S.qs("#er-assignee").value ? +S.qs("#er-assignee").value : null, end_date: S.qs("#er-end").value || null, active: S.qs("#er-active").checked };
      try { await S.api(`/api/boards/recurring/${r.id}`, { method: "PATCH", body }); S.toast("Recurring task updated", "ok"); m.close(); parent.close(); openBox(box.id); }
      catch (e) { S.toast(e.detail, "err"); }
    };
  }

  function editReconForm(r, box, parent) {
    const m = S.modal({
      title: "Edit reconciliation",
      body: `<label class="field"><span>Trigger</span><select id="ec-trigger">${vocab.recon_triggers.map((t) => `<option ${t === r.trigger_type ? "selected" : ""}>${t}</option>`).join("")}</select></label>
        <label class="field"><span>Description</span><textarea id="ec-desc">${S.esc(r.description || "")}</textarea></label>
        <label class="field"><span>Owner</span><select id="ec-owner"><option value="">—</option>${people.map((p) => `<option value="${p.id}" ${r.owner_id === p.id ? "selected" : ""}>${S.esc(p.name)}</option>`).join("")}</select></label>
        <div class="row" style="gap:10px">
          <label class="field" style="flex:1"><span>Status</span><select id="ec-status">${vocab.recon_statuses.map((s) => `<option ${s === r.status ? "selected" : ""}>${s}</option>`).join("")}</select></label>
        </div>
        <label class="field"><span>Resolution</span><textarea id="ec-res">${S.esc(r.resolution || "")}</textarea></label>`,
      footer: `<button class="btn ghost" id="ec-cancel">Cancel</button><button class="btn primary" id="ec-save">Save</button>`,
    });
    S.qs("#ec-cancel").onclick = m.close;
    S.qs("#ec-save").onclick = async () => {
      const body = { trigger_type: S.qs("#ec-trigger").value, description: S.qs("#ec-desc").value || null, owner_id: S.qs("#ec-owner").value ? +S.qs("#ec-owner").value : null, status: S.qs("#ec-status").value, resolution: S.qs("#ec-res").value || null };
      try { await S.api(`/api/boards/reconciliation/${r.id}`, { method: "PATCH", body }); S.toast("Reconciliation updated", "ok"); m.close(); parent.close(); openBox(box.id); loadBoard(); }
      catch (e) { S.toast(e.detail, "err"); }
    };
  }

  function placeholder(icon, title, text) {
    S.qs("#tt-body").innerHTML = `<div class="tt-placeholder">${S.ICON[icon] || ""}<h3>${title}</h3><p>${text}</p></div>`;
  }

  // Deep link from a notification: /tasks?box=<id>
  const boxParam = new URLSearchParams(location.search).get("box");
  if (boxParam) openBox(+boxParam);
};
