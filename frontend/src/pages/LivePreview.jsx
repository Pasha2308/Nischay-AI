import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Monitor,
  XCircle,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  Loader2,
} from "lucide-react";
import { API, INTERVALS } from "../config/api";

const STAGES = [
  { id: "crawl", label: "Crawl", icon: "🔍" },
  { id: "plan", label: "Plan", icon: "📋" },
  { id: "execute", label: "Execute", icon: "▶️" },
  { id: "detect", label: "Detect", icon: "🐛" },
  { id: "score", label: "Score", icon: "📊" },
  { id: "report", label: "Report", icon: "📄" },
];

const STAGE_MAP = {
  crawl: "crawl",
  crawling: "crawl",
  plan: "plan",
  planning: "plan",
  execute: "execute",
  executing: "execute",
  exec: "execute",
  detect: "detect",
  detecting: "detect",
  score: "score",
  scoring: "score",
  report: "report",
  reporting: "report",
  done: "report",
  completed: "report",
};

const STAGE_COLORS = {
  crawl: "#00D4FF",
  plan: "#7C3AED",
  execute: "#E6EDF3",
  detect: "#F5A623",
  score: "#00C896",
  report: "#00C896",
  error: "#FF4444",
};

function parseLogLine(rawLine) {
  const line = typeof rawLine === "string" ? rawLine : String(rawLine);
  const stageMatch = line.match(/\[(CRAWL|PLAN|EXEC(?:UTE)?|DETECT|SCORE|REPORT|ERROR)\]/i);
  const stage = stageMatch ? STAGE_MAP[stageMatch[1].toLowerCase()] ?? "execute" : "execute";
  const message = line
    .replace(/\[.*?\]\s*/, "")
    .replace(/\d{2}:\d{2}:\d{2}\s*—?\s*/, "")
    .trim();
  const timestamp = new Date().toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  return { stage, message, timestamp, raw: line };
}

export function LivePreview() {
  const { runId } = useParams();
  const navigate = useNavigate();

  const [logs, setLogs] = useState([]);
  const [currentStage, setCurrentStage] = useState("crawl");
  const [metrics, setMetrics] = useState({
    pagesFound: 0,
    actionsRun: 0,
    issuesFound: 0,
  });
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isComplete, setIsComplete] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [finalScore, setFinalScore] = useState(null);
  const [finalLevel, setFinalLevel] = useState(null);
  const [connectionMode, setConnectionMode] = useState("connecting");

  const logEndRef = useRef(null);
  const pollingRef = useRef(null);
  const sseRef = useRef(null);
  const sentLogCountRef = useRef(0);
  const timerRef = useRef(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  useEffect(() => {
    if (isComplete || hasError) return;
    timerRef.current = setInterval(() => {
      setElapsedSeconds((s) => s + 1);
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [isComplete, hasError]);

  const formatTime = (s) =>
    `${Math.floor(s / 60)
      .toString()
      .padStart(2, "0")}:${(s % 60).toString().padStart(2, "0")}`;

  const addLog = useCallback((logObj) => {
    setLogs((prev) => [...prev, { ...logObj, id: Date.now() + Math.random() }]);
  }, []);

  const handleComplete = useCallback(
    (score, level) => {
      setIsComplete(true);
      setFinalScore(score);
      setFinalLevel(level);
      setConnectionMode("complete");
      if (pollingRef.current) clearInterval(pollingRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
      addLog({
        stage: "score",
        message: `✓ Run complete — Risk Score: ${score} — ${level}`,
        timestamp: new Date().toLocaleTimeString(),
      });
    },
    [addLog]
  );

  const handleError = useCallback(
    (message) => {
      setHasError(true);
      setConnectionMode("error");
      if (pollingRef.current) clearInterval(pollingRef.current);
      addLog({
        stage: "error",
        message: `✗ ${message}`,
        timestamp: new Date().toLocaleTimeString(),
      });
    },
    [addLog]
  );

  const startPolling = useCallback(() => {
    if (!runId) return;
    setConnectionMode("polling");
    addLog({
      stage: "crawl",
      message: "Connected — polling for updates...",
      timestamp: new Date().toLocaleTimeString(),
    });

    pollingRef.current = setInterval(async () => {
      try {
        const statusRes = await fetch(API.getRunStatus(runId));
        if (statusRes.ok) {
          const status = await statusRes.json();
          const mappedStage = STAGE_MAP[status.stage] ?? status.stage ?? "crawl";
          setCurrentStage(mappedStage);
          setMetrics({
            pagesFound: status.pages_found ?? 0,
            actionsRun: status.actions_run ?? 0,
            issuesFound: status.issues_found ?? 0,
          });
          if (status.elapsed_seconds) setElapsedSeconds(status.elapsed_seconds);
          if (status.status === "completed") {
            handleComplete(status.risk_score ?? 0, status.risk_level ?? "LOW RISK");
            return;
          }
          if (status.status === "failed") {
            handleError(status.error ?? "Run failed");
            return;
          }
        }

        const logsRes = await fetch(API.getRunLogs(runId));
        if (logsRes.ok) {
          const logsData = await logsRes.json();
          const allLines = logsData.logs ?? [];
          const newLines = allLines.slice(sentLogCountRef.current);
          newLines.forEach((line) => addLog(parseLogLine(line)));
          sentLogCountRef.current = allLines.length;
        }
      } catch (err) {
        console.warn("Polling error:", err);
      }
    }, INTERVALS.livePreviewPoll);
  }, [runId, addLog, handleComplete, handleError]);

  const startSSE = useCallback(() => {
    if (!runId) return;
    setConnectionMode("sse");

    try {
      const es = new EventSource(API.streamRun(runId));
      sseRef.current = es;

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "connected") {
            addLog({
              stage: "crawl",
              message: "Connected to live stream — test starting...",
              timestamp: new Date().toLocaleTimeString(),
            });
          }

          if (data.type === "log") {
            const mappedStage = STAGE_MAP[data.stage] ?? "execute";
            setCurrentStage(mappedStage);
            addLog({
              stage: mappedStage,
              message: data.message,
              timestamp: data.timestamp,
            });
          }

          if (data.type === "metric") {
            setMetrics({
              pagesFound: data.pages_found ?? 0,
              actionsRun: data.actions_run ?? 0,
              issuesFound: data.issues_found ?? 0,
            });
            if (data.stage) {
              setCurrentStage(STAGE_MAP[data.stage] ?? data.stage);
            }
          }

          if (data.type === "stage_change") {
            setCurrentStage(STAGE_MAP[data.stage] ?? data.stage);
          }

          if (data.type === "complete") {
            es.close();
            handleComplete(data.risk_score, data.risk_level);
          }

          if (data.type === "error") {
            es.close();
            handleError(data.message);
          }

          if (data.type === "timeout") {
            es.close();
            startPolling();
          }
        } catch (parseErr) {
          console.warn("SSE parse error:", parseErr);
        }
      };

      es.onerror = () => {
        es.close();
        startPolling();
      };

      return () => es.close();
    } catch (err) {
      startPolling();
      return undefined;
    }
  }, [runId, addLog, handleComplete, handleError, startPolling]);

  useEffect(() => {
    if (!runId) return;

    addLog({
      stage: "crawl",
      message: `Connecting to run ${runId}...`,
      timestamp: new Date().toLocaleTimeString(),
    });

    const cleanup = startSSE();

    return () => {
      if (typeof cleanup === "function") cleanup();
      if (pollingRef.current) clearInterval(pollingRef.current);
      sseRef.current?.close();
    };
  }, [runId, addLog, startSSE]);

  if (!runId) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 md:ml-[240px]">
        <Monitor size={64} style={{ color: "#484F58" }} />
        <div className="text-center">
          <h2 style={{ fontFamily: "Syne,sans-serif", color: "#E6EDF3", fontSize: "24px", fontWeight: 700 }}>No Active Run</h2>
          <p style={{ color: "#8B949E", marginTop: "8px" }}>Start a new test to see live preview</p>
        </div>
        <button
          type="button"
          onClick={() => navigate("/new-test")}
          style={{
            background: "linear-gradient(135deg,#00D4FF,#7C3AED)",
            color: "#0A0C10",
            border: "none",
            borderRadius: "8px",
            padding: "12px 24px",
            fontFamily: "DM Sans,sans-serif",
            fontWeight: 600,
            cursor: "pointer",
            fontSize: "15px",
          }}
        >
          Start New Test
        </button>
      </div>
    );
  }

  const currentStageIndex = STAGES.findIndex((s) => s.id === currentStage);
  const fs = Number(finalScore) || 0;
  const riskColor = fs >= 81 ? "#FF4444" : fs >= 61 ? "#FF6B35" : fs >= 31 ? "#F5A623" : "#00C896";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: "16px", padding: "24px" }} className="md:ml-[240px]">
      <div style={{ background: "#0F1117", border: "1px solid #21262D", borderRadius: "12px", padding: "16px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          {STAGES.map((stage, i) => {
            const isDone = i < currentStageIndex;
            const isActive = i === currentStageIndex;
            return (
              <div key={stage.id} style={{ display: "flex", alignItems: "center", flex: i < STAGES.length - 1 ? 1 : "none" }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "6px" }}>
                  <div
                    style={{
                      width: "36px",
                      height: "36px",
                      borderRadius: "50%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      background: isDone ? "#00C896" : isActive ? "#00D4FF" : "#161B22",
                      border: `2px solid ${isDone ? "#00C896" : isActive ? "#00D4FF" : "#30363D"}`,
                      boxShadow: isActive ? "0 0 16px rgba(0,212,255,0.4)" : "none",
                      animation: isActive ? "pulse 2s ease-in-out infinite" : "none",
                      transition: "all 0.3s ease",
                    }}
                  >
                    {isDone ? <CheckCircle2 size={18} color="#0A0C10" /> : <span style={{ fontSize: "14px" }}>{stage.icon}</span>}
                  </div>
                  <span
                    style={{
                      fontFamily: "DM Sans,sans-serif",
                      fontSize: "11px",
                      color: isDone ? "#00C896" : isActive ? "#00D4FF" : "#484F58",
                      fontWeight: isActive ? 600 : 400,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {stage.label}
                  </span>
                </div>
                {i < STAGES.length - 1 && (
                  <div
                    style={{
                      flex: 1,
                      height: "2px",
                      margin: "0 8px",
                      marginBottom: "20px",
                      background: isDone ? "linear-gradient(90deg,#00C896,#00C896)" : "#21262D",
                      transition: "background 0.5s ease",
                    }}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      <AnimatePresence>
        {isComplete && (
          <motion.div
            initial={{ opacity: 0, y: -16 }}
            animate={{ opacity: 1, y: 0 }}
            style={{
              background: "rgba(0,200,150,0.1)",
              border: "1px solid rgba(0,200,150,0.4)",
              borderRadius: "12px",
              padding: "20px 24px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <CheckCircle2 size={28} color="#00C896" />
              <div>
                <div style={{ fontFamily: "Syne,sans-serif", fontWeight: 700, color: "#E6EDF3", fontSize: "18px" }}>QA Run Complete</div>
                <div style={{ color: "#8B949E", fontSize: "14px", marginTop: "2px" }}>
                  Risk Score:{" "}
                  <span style={{ color: riskColor, fontFamily: "JetBrains Mono,monospace", fontWeight: 600 }}>
                    {finalScore} — {finalLevel}
                  </span>
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => navigate(`/results/${runId}`)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                background: "linear-gradient(135deg,#00D4FF,#7C3AED)",
                color: "#0A0C10",
                border: "none",
                borderRadius: "8px",
                padding: "10px 20px",
                fontFamily: "DM Sans,sans-serif",
                fontWeight: 600,
                cursor: "pointer",
                fontSize: "14px",
              }}
            >
              View Full Results <ChevronRight size={16} />
            </button>
          </motion.div>
        )}
        {hasError && (
          <motion.div
            initial={{ opacity: 0, y: -16 }}
            animate={{ opacity: 1, y: 0 }}
            style={{
              background: "rgba(255,68,68,0.1)",
              border: "1px solid rgba(255,68,68,0.4)",
              borderRadius: "12px",
              padding: "20px 24px",
              display: "flex",
              alignItems: "center",
              gap: "12px",
            }}
          >
            <AlertTriangle size={28} color="#FF4444" />
            <div>
              <div style={{ fontFamily: "Syne,sans-serif", fontWeight: 700, color: "#FF4444", fontSize: "18px" }}>Run Failed</div>
              <div style={{ color: "#8B949E", fontSize: "14px", marginTop: "2px" }}>Check logs below for details</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: "16px", flex: 1, minHeight: 0 }}>
        <div style={{ background: "#0A0C10", border: "1px solid #21262D", borderRadius: "12px", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div
            style={{
              padding: "12px 16px",
              borderBottom: "1px solid #21262D",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <div style={{ width: 12, height: 12, borderRadius: "50%", background: "#FF4444" }} />
              <div style={{ width: 12, height: 12, borderRadius: "50%", background: "#F5A623" }} />
              <div style={{ width: 12, height: 12, borderRadius: "50%", background: "#00C896" }} />
              <span style={{ fontFamily: "JetBrains Mono,monospace", fontSize: "12px", color: "#484F58", marginLeft: "8px" }}>nischay-qa — {runId}</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              {connectionMode === "sse" && (
                <span style={{ fontSize: "11px", color: "#00C896" }}>● SSE Live</span>
              )}
              {connectionMode === "polling" && (
                <span style={{ fontSize: "11px", color: "#F5A623" }}>● Polling</span>
              )}
              {connectionMode === "connecting" && (
                <span style={{ fontSize: "11px", color: "#8B949E" }}>● Connecting...</span>
              )}
            </div>
          </div>

          <div
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "16px",
              fontFamily: "JetBrains Mono,monospace",
              fontSize: "13px",
              lineHeight: "1.6",
            }}
          >
            <AnimatePresence initial={false}>
              {logs.map((log) => (
                <motion.div
                  key={log.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.15 }}
                  style={{
                    display: "flex",
                    gap: "12px",
                    marginBottom: "4px",
                    color: STAGE_COLORS[log.stage] ?? "#E6EDF3",
                  }}
                >
                  <span style={{ color: "#484F58", minWidth: "60px", fontSize: "11px", paddingTop: "1px" }}>{log.timestamp}</span>
                  <span style={{ color: STAGE_COLORS[log.stage] ?? "#E6EDF3", wordBreak: "break-word" }}>{log.message}</span>
                </motion.div>
              ))}
            </AnimatePresence>
            {!isComplete && !hasError && (
              <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "#484F58", marginTop: "8px" }}>
                <Loader2 size={12} className="animate-spin" />
                <span style={{ fontSize: "12px" }}>Waiting for output...</span>
              </div>
            )}
            <div ref={logEndRef} />
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ background: "#0F1117", border: "1px solid #21262D", borderRadius: "12px", overflow: "hidden", flex: 1 }}>
            <div style={{ padding: "10px 12px", borderBottom: "1px solid #21262D", display: "flex", alignItems: "center", gap: "8px" }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#FF4444" }} />
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#F5A623" }} />
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#00C896" }} />
              <div
                style={{
                  flex: 1,
                  background: "#161B22",
                  borderRadius: "4px",
                  padding: "4px 10px",
                  fontSize: "11px",
                  fontFamily: "JetBrains Mono,monospace",
                  color: "#8B949E",
                }}
              >
                🔒 Playwright Browser Running
              </div>
            </div>
            <div style={{ padding: "24px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "200px", gap: "16px" }}>
              <div
                style={{
                  width: "60px",
                  height: "60px",
                  borderRadius: "50%",
                  background: "rgba(0,212,255,0.1)",
                  border: "2px solid rgba(0,212,255,0.3)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  animation: !isComplete ? "spin 3s linear infinite" : "none",
                }}
              >
                <Monitor size={28} color="#00D4FF" />
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontFamily: "DM Sans,sans-serif", fontWeight: 600, color: "#E6EDF3", fontSize: "14px" }}>
                  {isComplete ? "Test Complete" : "Browser Automation Active"}
                </div>
                <div style={{ color: "#8B949E", fontSize: "12px", marginTop: "4px" }}>
                  {isComplete ? "Playwright session closed" : "Playwright is running tests in real browser"}
                </div>
              </div>
              {!isComplete && (
                <div
                  style={{
                    fontSize: "12px",
                    color: "#484F58",
                    fontFamily: "JetBrains Mono,monospace",
                    background: "#161B22",
                    borderRadius: "6px",
                    padding: "8px 12px",
                    textAlign: "center",
                  }}
                >
                  Stage: {currentStage.toUpperCase()}
                </div>
              )}
            </div>
          </div>

          <div style={{ background: "#0F1117", border: "1px solid #21262D", borderRadius: "12px", padding: "16px" }}>
            <div
              style={{
                fontSize: "11px",
                color: "#484F58",
                fontFamily: "DM Sans,sans-serif",
                marginBottom: "8px",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
              }}
            >
              Latest Action
            </div>
            <div style={{ fontFamily: "JetBrains Mono,monospace", fontSize: "12px", color: "#00D4FF", wordBreak: "break-word" }}>
              {logs.length > 0 ? logs[logs.length - 1].message : "Waiting for test to start..."}
            </div>
          </div>
        </div>
      </div>

      <div
        style={{
          background: "#0F1117",
          border: "1px solid #21262D",
          borderRadius: "12px",
          padding: "16px 24px",
          display: "grid",
          gridTemplateColumns: "repeat(4,1fr)",
          gap: "16px",
        }}
      >
        {[
          { label: "Pages Found", value: metrics.pagesFound, color: "#00D4FF" },
          { label: "Actions Run", value: metrics.actionsRun, color: "#7C3AED" },
          {
            label: "Issues Found",
            value: metrics.issuesFound,
            color: metrics.issuesFound > 0 ? "#F5A623" : "#00C896",
          },
          { label: "Elapsed", value: formatTime(elapsedSeconds), color: "#8B949E" },
        ].map((m) => (
          <div key={m.label} style={{ textAlign: "center" }}>
            <div style={{ fontFamily: "JetBrains Mono,monospace", fontSize: "28px", fontWeight: 500, color: m.color, lineHeight: 1 }}>
              {m.value}
            </div>
            <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "12px", color: "#484F58", marginTop: "4px" }}>{m.label}</div>
          </div>
        ))}
      </div>

      {!isComplete && !hasError && (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            type="button"
            onClick={() => {
              if (window.confirm("Leave live view? The run continues on the server.")) {
                sseRef.current?.close();
                if (pollingRef.current) clearInterval(pollingRef.current);
                navigate("/history");
              }
            }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              background: "transparent",
              border: "1px solid rgba(255,68,68,0.4)",
              color: "#FF4444",
              borderRadius: "8px",
              padding: "8px 16px",
              fontFamily: "DM Sans,sans-serif",
              fontWeight: 500,
              cursor: "pointer",
              fontSize: "13px",
              transition: "all 0.2s",
            }}
          >
            <XCircle size={16} /> Abort Run
          </button>
        </div>
      )}
    </div>
  );
}
