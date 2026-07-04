/* Attendance kiosk + Super-Admin phone scanner.
   States: idle (auto-scan) → scanned (four big buttons) → confirm (auto-reset 5s).
   Offline: punches queue in IndexedDB and sync every 30s when back online. */
window.pageInit = async (S) => {
  const MODE = document.body.dataset.mode;         // "kiosk" | "scanner"
  const DEVICE = document.body.dataset.device;      // "kiosk" | "admin-phone"
  const stage = S.qs("#stage");
  const LATE_REASONS = ["Heavy traffic", "Medical", "Personal", "Client meeting", "Transport issue"];
  let scanner = null, scanning = false, resetTimer = null;

  // --- Scanner mode is Super-Admin only -----------------------------------
  if (MODE === "scanner") {
    try {
      const me = await S.api("/api/auth/me");
      if (me.role !== "super_admin") { S.toast("Super Admin only", "err"); setTimeout(() => (location.href = "/dashboard"), 1200); return; }
    } catch (e) { location.href = "/login"; return; }
  }

  // --- Online indicator ----------------------------------------------------
  function setOnline(on) {
    const el = S.qs("#online");
    el.className = "online " + (on ? "on" : "off");
    S.qs("#online-t").textContent = on ? "Online" : "Offline";
  }
  window.addEventListener("online", () => { setOnline(true); syncQueue(); });
  window.addEventListener("offline", () => setOnline(false));
  setOnline(navigator.onLine);

  // --- IndexedDB offline queue --------------------------------------------
  function db() {
    return new Promise((res, rej) => {
      const r = indexedDB.open("sentinel-kiosk", 1);
      r.onupgradeneeded = () => r.result.createObjectStore("queue", { keyPath: "id", autoIncrement: true });
      r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
    });
  }
  async function enqueue(p) { const d = await db(); return new Promise((res, rej) => { const tx = d.transaction("queue", "readwrite"); tx.objectStore("queue").add(p); tx.oncomplete = res; tx.onerror = () => rej(tx.error); }); }
  async function queued() { const d = await db(); return new Promise((res) => { const tx = d.transaction("queue", "readonly"); const q = tx.objectStore("queue").getAll(); q.onsuccess = () => res(q.result || []); }); }
  async function clearQueue() { const d = await db(); return new Promise((res) => { const tx = d.transaction("queue", "readwrite"); tx.objectStore("queue").clear(); tx.oncomplete = res; }); }
  async function queueCount() { return (await queued()).length; }

  async function syncQueue() {
    if (!navigator.onLine) return;
    const items = await queued();
    if (!items.length) return;
    try {
      const punches = items.map((i) => ({ token: i.token, action: i.action, client_time: i.client_time, late_reason: i.late_reason, handover_note: i.handover_note }));
      await S.api("/api/attendance/offline-sync", { method: "POST", body: { punches } });
      await clearQueue();
      S.toast(`Synced ${punches.length} offline punch(es)`, "ok");
      if (!scanning) idle();
    } catch (e) { /* stay queued; retry next tick */ }
  }
  setInterval(syncQueue, 30000);

  // --- Clock ---------------------------------------------------------------
  function clockHTML() {
    const now = new Date();
    return `<div class="k-clock" id="kclock">${now.toLocaleTimeString("en-PH", { timeZone: "Asia/Manila", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true })}</div>
      <div class="k-date">${now.toLocaleDateString("en-PH", { timeZone: "Asia/Manila", weekday: "long", month: "long", day: "numeric" })}</div>`;
  }
  let clockInt = setInterval(() => { const c = S.qs("#kclock"); if (c) c.textContent = new Date().toLocaleTimeString("en-PH", { timeZone: "Asia/Manila", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true }); }, 1000);

  // --- Idle: auto-scan -----------------------------------------------------
  async function idle() {
    clearTimeout(resetTimer);
    const qc = await queueCount();
    stage.innerHTML = `${clockHTML()}
      <div id="reader"></div>
      <div class="k-hint">Scan your Agora badge to punch ${MODE === "scanner" ? "(admin phone)" : ""}</div>
      <div class="manual"><input id="manual" placeholder="…or type badge code" autocomplete="off"><button class="btn primary" id="manual-go">Go</button></div>
      ${qc ? `<div class="queued">${qc} punch(es) waiting to sync</div>` : ""}
      ${MODE === "scanner" ? `<div style="margin-top:16px;border-top:1px solid var(--line);padding-top:14px">
        <button class="btn ghost" id="assign-qr">${S.ICON.qr}Generate / assign QR badge</button></div>` : ""}`;
    S.qs("#manual-go").onclick = () => { const t = S.qs("#manual").value.trim(); if (t) handleToken(t); };
    S.qs("#manual").onkeydown = (e) => { if (e.key === "Enter") S.qs("#manual-go").click(); };
    if (MODE === "scanner" && S.qs("#assign-qr")) S.qs("#assign-qr").onclick = openAssignQr;
    startScanner();
  }

  // --- Scanner-only: generate + assign a QR badge to an employee -----------
  async function openAssignQr() {
    await stopScanner();
    let people = [];
    try { people = await S.api("/api/people"); } catch (e) { S.toast(e.detail || "Couldn't load employees", "err"); idle(); return; }
    const m = S.modal({
      title: "Assign QR badge",
      body: `<label class="field"><span>Employee</span>
          <select id="qa-user"><option value="">Choose an employee…</option>${people.map((p) => `<option value="${p.id}">${S.esc(p.name)} — ${S.esc(p.role_label || p.role)}</option>`).join("")}</select></label>
        <div id="qa-preview" style="text-align:center;margin-top:8px"></div>`,
      footer: `<button class="btn ghost" id="qa-close">Close</button>`,
    });
    S.qs("#qa-close").onclick = () => { m.close(); idle(); };
    S.qs("#qa-user").onchange = (e) => {
      const id = e.target.value;
      const box = S.qs("#qa-preview");
      if (!id) { box.innerHTML = ""; return; }
      box.innerHTML = `
        <img alt="QR" src="/api/people/${id}/qr?t=${Date.now()}" style="width:190px;height:190px;border:1px solid var(--line);border-radius:12px;padding:8px;background:#fff">
        <div class="row" style="justify-content:center;gap:8px;margin-top:12px">
          <a class="btn ghost" href="/api/people/${id}/qr" download="badge-${id}.png">${S.ICON.download}Download / print</a>
          <button class="btn primary" id="qa-regen">Reissue new code</button>
        </div>
        <div class="muted" style="font-size:12px;margin-top:8px">This is the employee's badge. Print it or download to their phone; the kiosk reads it.</div>`;
      S.qs("#qa-regen").onclick = async () => {
        if (!confirm("Reissue a new QR code? The current badge will stop working.")) return;
        try {
          await S.api(`/api/people/${id}/qr/regenerate`, { method: "POST" });
          S.qs(`#qa-preview img`).src = `/api/people/${id}/qr?t=` + Date.now();
          S.toast("New badge issued", "ok");
        } catch (err) { S.toast(err.detail, "err"); }
      };
    };
  }

  function startScanner() {
    if (typeof Html5Qrcode === "undefined") return;
    try {
      scanner = new Html5Qrcode("reader");
      scanning = true;
      scanner.start({ facingMode: "environment" }, { fps: 10, qrbox: { width: 220, height: 220 } },
        (decoded) => { if (scanning) { scanning = false; handleToken(decoded); } },
        () => {}
      ).catch(() => { const r = S.qs("#reader"); if (r) r.style.display = "none"; });
    } catch (e) { const r = S.qs("#reader"); if (r) r.style.display = "none"; }
  }
  async function stopScanner() {
    scanning = false;
    if (scanner) { try { await scanner.stop(); scanner.clear(); } catch (e) {} scanner = null; }
  }

  // --- Handle a scanned/typed token ---------------------------------------
  async function handleToken(token) {
    await stopScanner();
    let info;
    try { info = await S.api("/api/attendance/scan", { method: "POST", body: { token } }); }
    catch (e) {
      // Offline? We can't resolve the token, but we can still queue a raw punch attempt is not possible without a chosen action. Show error.
      if (e.status === undefined) stage.innerHTML = confirmCard("err", "Offline", "Cannot look up badge while offline. Reconnect and try again.");
      else stage.innerHTML = confirmCard("err", "Not recognised", e.detail || "Unknown badge.");
      resetTimer = setTimeout(idle, 3500); return;
    }
    renderScanned(token, info);
  }

  function isLate(shift) {
    const now = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Manila" }));
    const [h, m] = (shift.start || "08:00").split(":").map(Number);
    const thr = new Date(now); thr.setHours(h, m + (shift.grace || 0), 0, 0);
    return now > thr;
  }

  function renderScanned(token, info) {
    const va = info.valid_actions;
    const btn = (action, cls, icon, label, enabled) =>
      `<button class="k-btn ${cls}" data-action="${action}" ${enabled ? "" : "disabled"}>${S.ICON[icon]}${label}</button>`;
    const stateLabel = { none: "Not clocked in", in: "Clocked in", on_break: "On break", out: "Clocked out" }[info.state];
    stage.innerHTML = `
      ${S.avatar(info.user, "lg")}
      <div class="k-name" style="margin-top:12px">${S.esc(info.user.name)}</div>
      <div class="k-sub">${S.esc(info.team_name || info.role_label)} · <span class="pill grey">${stateLabel}</span></div>
      <div class="k-actions">
        ${btn("clock_in", "in", "check", "Clock In", va.includes("clock_in"))}
        ${btn("break_start", "brk", "coffee", "Start Break", va.includes("break_start"))}
        ${btn("break_end", "endbrk", "clock", "End Break", va.includes("break_end"))}
        ${btn("clock_out", "out", "logout", "Clock Out", va.includes("clock_out"))}
      </div>
      <div id="extra" style="margin-top:16px"></div>
      <button class="btn ghost" id="cancel" style="margin-top:14px">Cancel</button>`;
    S.qs("#cancel").onclick = idle;
    S.qsa(".k-btn:not([disabled])").forEach((b) => b.onclick = () => onAction(token, info, b.dataset.action));
    resetTimer = setTimeout(idle, 20000); // auto-return if idle at the button screen
  }

  function onAction(token, info, action) {
    clearTimeout(resetTimer);
    const extra = S.qs("#extra");
    if (action === "clock_in" && isLate(info.shift)) {
      let reason = "";
      extra.innerHTML = `<div class="section-label">You're late — pick a reason</div>
        <div class="chips" id="chips">${LATE_REASONS.map((r) => `<span class="chip-sel" data-r="${S.esc(r)}">${S.esc(r)}</span>`).join("")}</div>
        <button class="btn success block" id="do" style="margin-top:14px">Confirm Clock In</button>`;
      S.qsa("#chips .chip-sel").forEach((c) => c.onclick = () => { S.qsa("#chips .chip-sel").forEach((x) => x.classList.remove("active")); c.classList.add("active"); reason = c.dataset.r; });
      S.qs("#do").onclick = () => submit(token, action, { late_reason: reason });
      return;
    }
    if (action === "clock_out") {
      extra.innerHTML = `<div class="section-label">Handover note (optional)</div>
        <textarea id="handover" placeholder="What should the next shift know?" style="margin-top:6px"></textarea>
        <button class="btn danger block" id="do" style="margin-top:12px">Confirm Clock Out</button>`;
      S.qs("#do").onclick = () => submit(token, action, { handover_note: S.qs("#handover").value });
      return;
    }
    submit(token, action, {});
  }

  async function submit(token, action, opts) {
    const payload = { token, action, device: DEVICE, late_reason: opts.late_reason || null, handover_note: opts.handover_note || null };
    const label = { clock_in: "Clocked in", clock_out: "Clocked out", break_start: "Break started", break_end: "Break ended" }[action];
    try {
      const res = await S.api("/api/attendance/event", { method: "POST", body: payload });
      const late = res.late_status === "Late" ? ` · ${res.late_minutes}m late` : "";
      stage.innerHTML = confirmCard("ok", label + "!", S.fmtTime(res.summary.clock_in || res.summary.clock_out) + late);
    } catch (e) {
      if (e.status === undefined) { // network failure → queue offline
        await enqueue({ token, action, client_time: new Date().toISOString(), late_reason: payload.late_reason, handover_note: payload.handover_note });
        stage.innerHTML = confirmCard("warn", "Saved offline", "Will sync automatically when back online.");
      } else {
        stage.innerHTML = confirmCard("err", "Couldn't punch", e.detail || "Try again.");
      }
    }
    resetTimer = setTimeout(idle, 5000);
  }

  function confirmCard(kind, title, sub) {
    const ic = kind === "ok" ? S.ICON.check : kind === "err" ? S.ICON.x : S.ICON.bell;
    const color = kind === "ok" ? "var(--green)" : kind === "err" ? "var(--danger)" : "var(--warn)";
    return `<div style="width:72px;height:72px;border-radius:50%;background:${color};color:#fff;display:grid;place-items:center;margin:6px auto 0">
        <span style="width:38px;height:38px">${ic}</span></div>
      <div class="big-status" style="margin-top:14px">${S.esc(title)}</div>
      <div class="k-sub">${S.esc(sub)}</div>
      <div class="k-hint">Returning to scan…</div>`;
  }

  idle();
  syncQueue();
};
