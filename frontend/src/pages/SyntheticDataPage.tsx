import { useMemo, useState } from "react";
import { generateSynthetic, type SyntheticDomain } from "../services/backend-service";

const DOMAINS: SyntheticDomain[] = ["ecommerce", "healthcare", "finance", "auth"];

function rowsToCsv(rows: Record<string, string | number>[]): string {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const esc = (v: string | number) => `"${String(v).replaceAll('"', '""')}"`;
  const body = rows.map((r) => headers.map((h) => esc(r[h] ?? "")).join(","));
  return [headers.join(","), ...body].join("\n");
}

export function SyntheticDataPage() {
  const [domain, setDomain] = useState<SyntheticDomain>("ecommerce");
  const [count, setCount] = useState(25);
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<Record<string, string | number>[]>([]);
  const [error, setError] = useState("");

  const preview = useMemo(() => rows.slice(0, 10), [rows]);
  const headers = useMemo(() => (preview.length ? Object.keys(preview[0]) : []), [preview]);

  async function onGenerate() {
    setLoading(true);
    setError("");
    try {
      const res = await generateSynthetic(domain, count);
      setRows(res.rows);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  function onDownloadCsv() {
    const csv = rowsToCsv(rows);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `synthetic_${domain}_${rows.length}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="page">
      <h2>Synthetic Data</h2>
      <div className="card">
        <div className="toolbar">
          <select value={domain} onChange={(e) => setDomain(e.target.value as SyntheticDomain)}>
            {DOMAINS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <div className="slider-wrap">
            <label>Count: {count}</label>
            <input
              type="range"
              min={1}
              max={200}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
            />
          </div>
          <button onClick={onGenerate} disabled={loading}>
            {loading ? "Generating..." : "Generate"}
          </button>
          <button onClick={onDownloadCsv} disabled={!rows.length}>
            Download CSV
          </button>
        </div>
        {error && <p className="muted">{error}</p>}
      </div>

      <div className="card">
        <div className="card-title">Preview (first 10 rows)</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {headers.map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.map((r, idx) => (
                <tr key={`row-${idx}`}>
                  {headers.map((h) => (
                    <td key={`${idx}-${h}`}>{String(r[h] ?? "")}</td>
                  ))}
                </tr>
              ))}
              {!preview.length && (
                <tr>
                  <td colSpan={Math.max(1, headers.length)} className="muted">
                    No data generated yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

