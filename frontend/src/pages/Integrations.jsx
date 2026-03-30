import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { GlassCard } from "../components/ui/GlassCard";

const CARDS = [
  { group: "CI/CD PIPELINES", items: ["GitHub Actions", "GitLab CI", "Jenkins", "CircleCI"] },
  { group: "COMMUNICATION", items: ["Slack", "Microsoft Teams", "Discord", "Email"] },
  { group: "PROJECT MANAGEMENT", items: ["Jira", "Linear", "Trello", "Asana"] },
  { group: "MONITORING", items: ["Webhook", "Zapier", "PagerDuty", "Datadog"] },
];

export function Integrations() {
  const [open, setOpen] = useState(null); // { type: 'github' | 'comingSoon' | 'apiKey', name?: string, created?: any }
  const [apiKeys, setApiKeys] = useState([]);
  const baseUrl = useMemo(() => {
    if (typeof window !== "undefined" && window.location && window.location.hostname) {
      const h = window.location.hostname;
      if (h === "localhost" || h === "127.0.0.1") return "http://localhost:8000";
    }
    return "https://api.nischay.ai";
  }, []);

  async function refreshKeys() {
    try {
      const res = await fetch(`${baseUrl}/api-keys`);
      const data = await res.json();
      setApiKeys(Array.isArray(data) ? data : []);
    } catch {
      setApiKeys([]);
    }
  }

  useEffect(() => {
    refreshKeys();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseUrl]);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <div className="font-display text-2xl font-extrabold">Integrations</div>

      {CARDS.map((g) => (
        <div key={g.group} className="grid gap-3">
          <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
            {g.group}
          </div>
          <div className="grid gap-4 md:grid-cols-4">
            {g.items.map((name) => (
              <GlassCard key={name} className="p-5 hover:scale-[1.01]">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-display font-bold">{name}</div>
                    <div className="text-sm mt-2" style={{ color: "var(--text-secondary)" }}>
                      Available
                    </div>
                  </div>
                  <div className="h-10 w-10 rounded-xl grid place-items-center" style={{ background: "rgba(124,58,237,0.12)", border: "1px solid rgba(48,54,61,0.65)", color: "var(--accent-violet)" }}>
                    {name.slice(0, 1)}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setOpen(name === "GitHub Actions" ? { type: "github" } : { type: "comingSoon", name })}
                  className="mt-4 h-10 w-full rounded-xl font-semibold"
                  style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
                >
                  Connect
                </button>
              </GlassCard>
            ))}
          </div>
        </div>
      ))}

      <GlassCard className="p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="font-display font-bold text-lg">REST API</div>
            <div className="text-sm mt-2" style={{ color: "var(--text-secondary)" }}>
              Base URL: <span className="font-mono" style={{ color: "var(--accent-cyan)" }}>{baseUrl}</span>
            </div>
          </div>
          <a
            href={`${baseUrl}/docs`}
            target="_blank"
            rel="noreferrer"
            className="h-11 px-4 rounded-xl font-semibold inline-flex items-center gap-2"
            style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}
          >
            View API Docs <ExternalLink size={16} />
          </a>
        </div>

        <div className="mt-4 grid gap-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
              API Keys
            </div>
            <button
              type="button"
              onClick={async () => {
                const name = "CI/CD Pipeline Key";
                const res = await fetch(`${baseUrl}/api-keys`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ name }),
                });
                const data = await res.json();
                if (res.ok && data?.api_key) {
                  setOpen({ type: "apiKey", created: data });
                  refreshKeys();
                } else {
                  setOpen({ type: "apiKey", created: { error: data?.detail || "Failed to generate key" } });
                }
              }}
              className="h-10 px-3 rounded-xl font-semibold"
              style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}
            >
              Generate API Key
            </button>
          </div>

          <div className="grid gap-2">
            {apiKeys.length ? (
              apiKeys.map((k) => (
                <div key={k.id} className="glass px-3 py-2 flex items-center justify-between gap-3">
                  <div className="grid">
                    <div className="font-display font-bold">{k.name}</div>
                    <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                      {k.key_prefix} · created {k.created_at ? new Date(k.created_at).toLocaleString() : "—"} · last used{" "}
                      {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "—"}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={async () => {
                      await fetch(`${baseUrl}/api-keys/${k.id}`, { method: "DELETE" });
                      refreshKeys();
                    }}
                    className="h-9 px-3 rounded-xl font-semibold"
                    style={{ background: "rgba(124,58,237,0.16)", color: "var(--accent-violet)", border: "1px solid rgba(124,58,237,0.35)" }}
                  >
                    Revoke
                  </button>
                </div>
              ))
            ) : (
              <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                No API keys yet.
              </div>
            )}
          </div>

          <div className="grid gap-2 mt-2">
            <div className="font-display font-bold">Code snippets</div>
            <pre className="glass p-3 text-xs overflow-auto" style={{ color: "var(--text-secondary)" }}>{`# cURL
curl -X POST "${baseUrl}/v1/scan" \\
  -H "Authorization: Bearer <YOUR_API_KEY>" \\
  -H "Content-Type: application/json" \\
  -d '{ "url": "https://example.com", "flows": ["auth","browse","cart"] }'`}</pre>
            <pre className="glass p-3 text-xs overflow-auto" style={{ color: "var(--text-secondary)" }}>{`# Python
import time, requests

BASE="${baseUrl}"
KEY="<YOUR_API_KEY>"

r=requests.post(f"{BASE}/v1/scan", headers={"Authorization": f"Bearer {KEY}"}, json={"url":"https://example.com","flows":["auth","browse","cart"]})
scan_id=r.json()["scan_id"]

while True:
  s=requests.get(f"{BASE}/v1/scan/{scan_id}", headers={"Authorization": f"Bearer {KEY}"}).json()
  if s["status"] in ("complete","failed"):
    break
  time.sleep(5)

report=requests.get(f"{BASE}/v1/scan/{scan_id}/report", headers={"Authorization": f"Bearer {KEY}"}).json()
print(report.get("risk_score"))`}</pre>
          </div>
        </div>
      </GlassCard>

      {open ? <Modal baseUrl={baseUrl} open={open} onClose={() => setOpen(null)} /> : null}
    </motion.div>
  );
}

function Modal({ open, onClose, baseUrl }) {
  const [email, setEmail] = useState("");
  const title =
    open.type === "github"
      ? "Add to your GitHub workflow"
      : open.type === "apiKey"
      ? "API Key"
      : `${open.name} integration coming soon`;

  const ghYaml = `name: Nischay AI Scan
on:
  push:
    branches: [ "main" ]

jobs:
  nischay-scan:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger scan
        id: trigger
        run: |
          set -e
          resp=$(curl -s -X POST "${baseUrl}/v1/scan" \\
            -H "Authorization: Bearer $NISCHAY_API_KEY" \\
            -H "Content-Type: application/json" \\
            -d '{"url":"${'{{'} github.server_url }}/${'{{'} github.repository }}","flows":["auth","browse","cart","checkout"]}')
          echo "$resp"
          scan_id=$(echo "$resp" | python -c "import sys, json; print(json.load(sys.stdin)['scan_id'])")
          echo "scan_id=$scan_id" >> $GITHUB_OUTPUT
      - name: Wait for completion
        id: wait
        run: |
          set -e
          scan_id="${'{{'} steps.trigger.outputs.scan_id }}"
          for i in $(seq 1 60); do
            s=$(curl -s "${baseUrl}/v1/scan/$scan_id" -H "Authorization: Bearer $NISCHAY_API_KEY")
            status=$(echo "$s" | python -c "import sys, json; print(json.load(sys.stdin).get('status',''))")
            echo "Status: $status"
            if [ "$status" = "complete" ] || [ "$status" = "failed" ]; then
              break
            fi
            sleep 10
          done
          report=$(curl -s "${baseUrl}/v1/scan/$scan_id/report" -H "Authorization: Bearer $NISCHAY_API_KEY")
          risk=$(echo "$report" | python -c "import sys, json; print(int(json.load(sys.stdin).get('risk_score',0) or 0))")
          echo "risk_score=$risk" >> $GITHUB_OUTPUT
          echo "report_json<<EOF" >> $GITHUB_OUTPUT
          echo "$report" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT
      - name: Fail on high risk
        run: |
          risk="${'{{'} steps.wait.outputs.risk_score }}"
          echo "Risk score: $risk"
          if [ "$risk" -gt 70 ]; then
            echo "Risk score above threshold (70) — failing workflow."
            exit 1
          fi
      - name: Comment report link (PRs only)
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const scanId = "${'{{'} steps.trigger.outputs.scan_id }}";
            const body = \`Nischay AI scan completed. Report: ${baseUrl}/v1/scan/\${scanId}/report\`;
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body,
            });
env:
  NISCHAY_API_KEY: ${'{{'} secrets.NISCHAY_API_KEY }}`;

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0" style={{ background: "rgba(10,12,16,0.65)", backdropFilter: "blur(6px)" }} onClick={onClose} />
      <div className="absolute left-1/2 top-1/2 w-[min(720px,92vw)] -translate-x-1/2 -translate-y-1/2 glass p-5">
        <div className="font-display text-xl font-bold">{title}</div>
        {open.type === "github" ? (
          <div className="mt-3 grid gap-3">
            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
              Copy this into <span className="font-mono">.github/workflows/nischay-scan.yml</span>. Add{" "}
              <span className="font-mono">NISCHAY_API_KEY</span> in repo secrets.
            </div>
            <pre className="glass p-3 text-xs overflow-auto" style={{ color: "var(--text-secondary)" }}>{ghYaml}</pre>
          </div>
        ) : open.type === "apiKey" ? (
          <div className="mt-3 grid gap-3">
            {open.created?.api_key ? (
              <>
                <div className="text-sm" style={{ color: "var(--warning)" }}>
                  Copy this key now. It will never be shown again.
                </div>
                <div className="glass px-3 py-2 flex items-center justify-between gap-3">
                  <span className="font-mono text-sm" style={{ color: "var(--text-secondary)" }}>{open.created.api_key}</span>
                  <button
                    type="button"
                    onClick={() => navigator.clipboard.writeText(open.created.api_key)}
                    className="h-10 px-3 rounded-xl font-semibold"
                    style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
                  >
                    Copy
                  </button>
                </div>
              </>
            ) : (
              <div className="text-sm" style={{ color: "var(--warning)" }}>
                {open.created?.error || "Could not generate key."}
              </div>
            )}
          </div>
        ) : (
          <div className="mt-3 grid gap-3">
            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
              Join the waitlist to be notified when it&apos;s ready.
            </div>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              className="h-11 rounded-xl px-3 outline-none"
              style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}
            />
            <button
              type="button"
              onClick={async () => {
                await fetch(`${baseUrl}/integrations/waitlist`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ integration: open.name, email }),
                });
                onClose();
              }}
              className="h-11 rounded-xl font-semibold"
              style={{ background: "linear-gradient(135deg, #00D4FF, #7C3AED)", color: "#0A0C10" }}
            >
              Notify me
            </button>
          </div>
        )}

        <button
          type="button"
          onClick={onClose}
          className="mt-4 h-11 w-full rounded-xl font-semibold"
          style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
        >
          Close
        </button>
      </div>
    </div>
  );
}

