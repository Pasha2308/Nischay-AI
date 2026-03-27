import { useEffect, useState } from "react";
import {
  loadReqonSettings,
  saveReqonSettings,
  testReqonConnection,
  type ReqonSettings,
} from "../services/reqon-integration";

export function SettingsPage() {
  const [settings, setSettings] = useState<ReqonSettings>({ apiKey: "", webhook: "" });
  const [testing, setTesting] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    setSettings(loadReqonSettings());
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 2200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  function onChange<K extends keyof ReqonSettings>(key: K, value: ReqonSettings[K]) {
    const next = { ...settings, [key]: value };
    setSettings(next);
    saveReqonSettings(next);
  }

  async function onTestConnection() {
    setTesting(true);
    const res = await testReqonConnection(settings);
    setToast(res.message);
    setTesting(false);
  }

  return (
    <div className="page">
      <h2>Settings</h2>
      <div className="card">
        <div className="settings-grid">
          <label>
            ReQon API Key
            <input
              type="password"
              value={settings.apiKey}
              onChange={(e) => onChange("apiKey", e.target.value)}
              placeholder="rqon_live_xxxxxxxxx"
            />
          </label>
          <label>
            ReQon Webhook URL
            <input
              type="url"
              value={settings.webhook}
              onChange={(e) => onChange("webhook", e.target.value)}
              placeholder="https://api.reqon.ai/webhooks/scan-events"
            />
          </label>
        </div>
        <div className="toolbar">
          <button onClick={onTestConnection} disabled={testing}>
            {testing ? "Testing..." : "Test Connection"}
          </button>
          <span className="muted">Connection is mocked for demo.</span>
        </div>
      </div>
      {toast && <div className="toast success">{toast}</div>}
    </div>
  );
}

