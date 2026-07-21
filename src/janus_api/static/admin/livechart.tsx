import React, { useEffect, useState, useRef } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

export default function LiveChart({ metricKey = "inbound_bytes" }) {
  const [data, setData] = useState([]); // array of {ts: ..., value: ...}
  const wsRef = useRef(null);

  useEffect(() => {
    const url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/monitor";
    const ws = new WebSocket(url);
    ws.onopen = () => console.log("ws open");
    ws.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        if (payload.type === "metrics_point") {
          const { point } = payload;
          const v = point.values[metricKey] ?? null;
          if (v !== null && v !== undefined) {
            setData((prev) => {
              const next = [...prev, { ts: new Date(point.ts * 1000).toLocaleTimeString(), value: Number(v) }];
              if (next.length > 60) next.shift();
              return next;
            });
          }
        }
      } catch (e) { console.error(e); }
    };
    ws.onclose = () => console.log("ws closed");
    ws.onerror = (e) => console.error(e);
    wsRef.current = ws;
    return () => {
      ws.close();
    };
  }, [metricKey]);

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data}>
        <XAxis dataKey="ts" />
        <YAxis />
        <Tooltip />
        <Legend />
        <Line type="monotone" dataKey="value" stroke="#8884d8" isAnimationActive={true} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}