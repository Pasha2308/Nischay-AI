import type { ScanRecord } from "../types";

const KEY = "reqon_scan_history_v1";

export function loadScans(): ScanRecord[] {
  const raw = localStorage.getItem(KEY);
  if (raw) {
    try {
      return JSON.parse(raw) as ScanRecord[];
    } catch {
      return [];
    }
  }
  return [];
}

export function saveScans(scans: ScanRecord[]) {
  localStorage.setItem(KEY, JSON.stringify(scans));
}

export function upsertScan(scan: ScanRecord) {
  const scans = loadScans();
  const idx = scans.findIndex((s) => s.id === scan.id);
  if (idx >= 0) scans[idx] = scan;
  else scans.unshift(scan);
  saveScans(scans);
  return scans;
}

