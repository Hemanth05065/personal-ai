import React, { useState } from "react";
import { request, setCsrf, json } from "../api.js";

const COPY = {
  bootstrap: { title: "Create your administrator account", text: "This is the first run. The account is stored only in the database on this computer." },
  login: { title: "Sign in", text: "Sign in from this registered device." },
  offline: { title: "Can’t reach the local API", text: "Start the backend, then reload this page." },
  loading: { title: "Checking the local security state", text: "" },
};

export default function AuthScreen({ mode, error: initialError, onSignedIn, onRetry }) {
  const [draft, setDraft] = useState({ username: "", password: "", device_name: "Local browser" });
  const [error, setError] = useState(initialError || "");
  const [busy, setBusy] = useState(false);
  const copy = COPY[mode] || COPY.loading;
  const isBootstrap = mode === "bootstrap";
  const update = (field) => (event) => setDraft({ ...draft, [field]: event.target.value });

  async function submit(event) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const data = await request(isBootstrap ? "/auth/bootstrap" : "/auth/login", { method: "POST", body: json(draft) });
      setCsrf(data.csrf_token);
      onSignedIn(data.user);
    } catch (problem) { setError(problem.message); }
    finally { setBusy(false); }
  }

  return <main className="auth">
    <div className="auth-card">
      <p className="brand-name">Local Assistant</p>
      <h1>{copy.title}</h1>
      {copy.text && <p className="muted">{copy.text}</p>}
      {error && <p className="field-error" role="alert">{error}</p>}
      {["bootstrap", "login"].includes(mode) && <form className="form" onSubmit={submit}>
        <label>Username
          <input required minLength={3} autoComplete="username" value={draft.username} onChange={update("username")} />
        </label>
        <label>Password
          <input required type="password" minLength={isBootstrap ? 12 : 1} autoComplete={isBootstrap ? "new-password" : "current-password"} value={draft.password} onChange={update("password")} aria-describedby={isBootstrap ? "pw-hint" : undefined} />
          {isBootstrap && <small id="pw-hint">At least 12 characters.</small>}
        </label>
        <label>Device name
          <input required value={draft.device_name} onChange={update("device_name")} aria-describedby="device-hint" />
          <small id="device-hint">Sessions are tied to this device.</small>
        </label>
        <button className="btn btn-primary" disabled={busy}>{busy ? "Working..." : isBootstrap ? "Create administrator" : "Sign in"}</button>
      </form>}
      {mode === "offline" && <button type="button" className="btn btn-primary" onClick={onRetry}>Try again</button>}
    </div>
  </main>;
}
