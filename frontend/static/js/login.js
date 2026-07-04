window.pageInit = async (S) => {
  const err = S.qs("#err");
  const showErr = (m) => { err.textContent = m; err.classList.add("show"); };

  // Surface Google callback errors (?error=...)
  const q = new URLSearchParams(location.search);
  if (q.get("error") === "noaccount") showErr("That Google account isn't registered. Ask an admin to add you first.");
  else if (q.get("error") === "google") showErr("Google sign-in failed. Please try again.");

  // Which methods are available?
  let cfg = { google_enabled: false, dev_login_enabled: false };
  try { cfg = await S.api("/api/auth/config"); } catch (e) {}
  if (!cfg.google_enabled) {
    const gw = S.qs("#google-wrap"); if (gw) gw.style.display = "none";  // hide until OAuth is configured
  }
  if (cfg.dev_login_enabled) {
    S.qs("#devwrap").style.display = "block";
    try {
      const users = await S.api("/api/auth/dev-users");
      S.qs("#user-select").innerHTML = users.map((u) => `<option value="${u.id}">${S.esc(u.name)} — ${S.esc(u.role.replace("_", " "))}</option>`).join("");
      S.qs("#devsignin").onclick = async () => {
        try { await S.api("/api/auth/dev-login", { method: "POST", body: { user_id: Number(S.qs("#user-select").value) } }); location.href = "/dashboard"; }
        catch (e) { showErr(e.detail || "Dev sign in failed"); }
      };
    } catch (e) {}
  }

  // Password login.
  S.qs("#login-form").onsubmit = async (e) => {
    e.preventDefault();
    err.classList.remove("show");
    const btn = S.qs("#signin"); btn.disabled = true; btn.textContent = "Signing in…";
    try {
      await S.api("/api/auth/login", { method: "POST", body: { email: S.qs("#email").value.trim(), password: S.qs("#password").value } });
      location.href = "/dashboard";
    } catch (e2) {
      showErr(e2.detail || "Invalid email or password");
      btn.disabled = false; btn.textContent = "Sign in";
    }
  };
};
