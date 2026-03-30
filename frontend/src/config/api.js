/**
 * Central API configuration for Nischay AI frontend.
 * All API calls must import endpoints from here.
 * Change BASE_URL once here — updates everywhere.
 */

export const BASE_URL =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const API = {
  health: `${BASE_URL}/health`,
  runTest: `${BASE_URL}/api/run`,
  getRuns: `${BASE_URL}/api/runs`,
  getRun: (id) => `${BASE_URL}/api/runs/${id}`,
  getRunStatus: (id) => `${BASE_URL}/api/runs/${id}/status`,
  getRunLogs: (id) => `${BASE_URL}/api/runs/${id}/logs`,
  streamRun: (id) => `${BASE_URL}/api/runs/${id}/stream`,
  compareRun: (id) => `${BASE_URL}/api/runs/${id}/compare`,
  rerun: (id) => `${BASE_URL}/api/runs/${id}/rerun`,
  abortRun: (id) => `${BASE_URL}/api/runs/${id}/abort`,
  getModules: `${BASE_URL}/api/modules`,
  getScreenshots: (id) => `${BASE_URL}/api/runs/${id}/screenshots`,
  getScreenshot: (id, filename) =>
    `${BASE_URL}/api/runs/${id}/screenshots/${filename}`,
};

export const INTERVALS = {
  livePreviewPoll: 1500,
  historyRefresh: 8000,
  resultsPoll: 2000,
  healthCheck: 15000,
};
