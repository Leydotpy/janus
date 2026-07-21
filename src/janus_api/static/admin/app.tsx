import React from "react";
import LiveChart from "./components/LiveChart";

export default function App() {
  return (
    <div style={{ padding: 24 }}>
      <h2>Janus Monitor (Live)</h2>
      <LiveChart metricKey="inbound_bytes" />
    </div>
  );
}