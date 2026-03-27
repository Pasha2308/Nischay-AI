import type { ScanRecord } from "../types";

export type ReqonSettings = {
  apiKey: string;
  webhook: string;
};

const KEY = "reqon_integration_settings_v1";

export function loadReqonSettings(): ReqonSettings {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { apiKey: "", webhook: "" };
    const parsed = JSON.parse(raw) as Partial<ReqonSettings>;
    return {
      apiKey: parsed.apiKey ?? "",
      webhook: parsed.webhook ?? "",
    };
  } catch {
    return { apiKey: "", webhook: "" };
  }
}

export function saveReqonSettings(settings: ReqonSettings): void {
  localStorage.setItem(KEY, JSON.stringify(settings));
}

async function mockDelay(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export async function testReqonConnection(_: ReqonSettings): Promise<{ ok: boolean; message: string }> {
  await mockDelay(800);
  return { ok: true, message: "Connected to ReQon successfully." };
}

export async function pushScanToReqon(_: ScanRecord, __: ReqonSettings): Promise<{ ok: boolean; message: string }> {
  await mockDelay(900);
  return { ok: true, message: "Scan pushed to ReQon successfully." };
}

