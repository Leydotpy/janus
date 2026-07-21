import React, { useEffect, useRef, useState } from "react";

const LEVEL_COLORS = {
  DEBUG: "var(--debug)",
  INFO: "var(--info)",
  WARNING: "var(--warning)",
  ERROR: "var(--error)",
  CRITICAL: "var(--critical)",
  UNKNOWN: "var(--unknown)",
};

function getColorForLevel(level) {
  if (!level) return LEVEL_COLORS.UNKNOWN;
  return LEVEL_COLORS[level.toUpperCase()] || LEVEL_COLORS.UNKNOWN;
}

export default function App() {
  const [logs, setLogs] = useState([]);
  const [filterLevel, setFilterLevel] = useState("ALL");
  const [autoScroll, setAutoScroll] = useState(true);
  const listRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    // initial fetch
    fetch("/logs?tail=200")
      .then((r) => r.json())
      .then((data) => {
        setLogs(data.logs || []);
      })
      .catch((e) => console.error("fetch logs:", e));
    // connect websocket
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${location.host}/ws/logs?last_n=50`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onmessage = (evt) => {
      try {
        const obj = JSON.parse(evt.data);
        setLogs((prev) => {
          const next = [...prev, obj];
          // keep cap to 1000 logs to avoid memory blowup
          if (next.length > 2000) next.splice(0, next.length - 2000);
          return next;
        });
      } catch (err) {
        console.error("ws parse:", err);
      }
    };
    ws.onclose = () => console.log("ws closed");
    ws.onerror = (e) => console.error("ws error", e);
    // send occasional ping so server's receive_text doesn't time out while we're idle
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 30000);
    return () => {
      clearInterval(pingInterval);
      if (ws && ws.readyState === WebSocket.OPEN) ws.close();
    };
  }, []);

  useEffect(() => {
    if (autoScroll && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const displayed = logs.filter((l) => {
    if (filterLevel === "ALL") return true;
    const lvl = (l.level || l.levelname || "UNKNOWN").toUpperCase();
    return lvl === filterLevel;
  });

  return (
    <div className="app">
      <header>
        <h1>Log Viewer</h1>
        <div className="controls">
          <label>
            Level:
            <select value={filterLevel} onChange={(e) => setFilterLevel(e.target.value)}>
              <option value="ALL">ALL</option>
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
              <option value="CRITICAL">CRITICAL</option>
            </select>
          </label>
          <label>
            <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} />
            Auto-scroll
          </label>
        </div>
      </header>

      <main>
        <div className="log-list" ref={listRef}>
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Level</th>
                <th>Logger</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {displayed.map((entry, i) => {
                const level = (entry.level || entry.levelname || "UNKNOWN").toUpperCase();
                const color = getColorForLevel(level);
                return (
                  <tr key={i} style={{ borderLeft: `4px solid ${color}` }}>
                    <td className="ts">{entry.timestamp || ""}</td>
                    <td className="level">{level}</td>
                    <td className="logger">{entry.logger || ""}</td>
                    <td className="msg">
                      <pre>{(entry.message || entry.raw || "").slice(0, 500)}</pre>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </main>

      <footer>
        Showing {displayed.length} logs — source: <code>{LOG_PATH}</code>
      </footer>
    </div>
  );
}