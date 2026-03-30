import { useEffect, useMemo, useState } from "react";
import { mockRuns, mockRunDetail } from "../data/mockData";

const BASE_URL = "http://localhost:8000";

function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function safeFetchJson(path, options) {
  const res = await fetch(`${BASE_URL}${path}`, options);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const text = await res.text();
  const data = safeJsonParse(text);
  if (data === null) throw new Error("Invalid JSON");
  return data;
}

export function useApi() {
  const [usingDemo, setUsingDemo] = useState(false);

  const api = useMemo(() => {
    return {
      usingDemo,
      setUsingDemo,
      async health() {
        try {
          const data = await safeFetchJson("/health");
          setUsingDemo(false);
          return data;
        } catch {
          setUsingDemo(true);
          return { status: "ok", version: "1.0.0" };
        }
      },
      async listRuns() {
        try {
          const data = await safeFetchJson("/api/runs");
          setUsingDemo(false);
          return Array.isArray(data) ? data : data?.runs ?? [];
        } catch {
          setUsingDemo(true);
          return mockRuns.map((r) => ({
            run_id: r.id,
            url: r.url,
            status: r.status,
            risk_score: r.risk_score,
            risk_level: r.risk_level,
            summary: r.summary,
            results: r.results,
            created_at: r.date,
            duration: r.duration,
          }));
        }
      },
      async createRun(body) {
        try {
          const data = await safeFetchJson("/api/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          setUsingDemo(false);
          return data;
        } catch {
          setUsingDemo(true);
          return {
            run_id: mockRunDetail.run_id,
            status: mockRunDetail.status,
            risk_score: mockRunDetail.risk_score,
            risk_level: mockRunDetail.risk_level,
            summary: mockRunDetail.summary,
            results: mockRunDetail.results,
          };
        }
      },
      async getRun(runId) {
        try {
          const data = await safeFetchJson(`/api/runs/${encodeURIComponent(runId)}`);
          setUsingDemo(false);
          return data;
        } catch {
          setUsingDemo(true);
          return {
            run_id: mockRunDetail.run_id,
            url: "https://shopify-demo.myshopify.com",
            status: mockRunDetail.status,
            risk_score: mockRunDetail.risk_score,
            risk_level: mockRunDetail.risk_level,
            summary: mockRunDetail.summary,
            results: mockRunDetail.results,
            report: mockRunDetail.report,
          };
        }
      },
      async getRunLogs(runId) {
        try {
          const res = await fetch(`${BASE_URL}/api/runs/${encodeURIComponent(runId)}/logs`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const text = await res.text();
          setUsingDemo(false);
          return text;
        } catch {
          setUsingDemo(true);
          return [
            "[CRAWL] Starting crawl: https://example.com",
            "[CRAWL] Discovered 12 pages",
            "[PLAN] Generating test plan...",
            "[EXEC] Navigating to /login",
            "[DETECT] ⚠ Console error on /checkout",
            "[DETECT] ✗ Broken image found: /images/hero.jpg",
            "[SCORE] Risk Score: 67 — HIGH RISK",
          ].join("\n");
        }
      },
      async compareRun(runId) {
        try {
          const data = await safeFetchJson(`/api/runs/${encodeURIComponent(runId)}/compare`);
          setUsingDemo(false);
          return data;
        } catch {
          setUsingDemo(true);
          return { new_issues: mockIssuesSlice(2), resolved_issues: mockIssuesSlice(1), regression_score_delta: +8 };
        }
      },
    };
  }, [usingDemo]);

  return api;
}

function mockIssuesSlice(n) {
  return Array.from({ length: n }).map((_, i) => ({
    id: `iss_demo_${i + 1}`,
    severity: i === 0 ? "HIGH" : "MEDIUM",
    type: "Demo Issue",
    url: "/demo",
    element: "body",
    description: "Demo issue (API unavailable).",
  }));
}

export function useRuns(onLoad = true) {
  const api = useApi();
  const [loading, setLoading] = useState(false);
  const [runs, setRuns] = useState([]);

  useEffect(() => {
    if (!onLoad) return;
    let alive = true;
    (async () => {
      setLoading(true);
      const list = await api.listRuns();
      if (alive) setRuns(list);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [api, onLoad]);

  return { api, loading, runs, setRuns };
}

