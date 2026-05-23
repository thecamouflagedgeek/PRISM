// src/pages/ProcessingPage.jsx
import { useState, useEffect } from "react";

const STAGES = [
  { icon: "📄", label: "Parsing documents",        sub: "pdfplumber extracting transaction rows" },
  { icon: "✅", label: "Validating fields",         sub: "Null checks · type checks · range checks" },
  { icon: "⚙️",  label: "Engineering features",     sub: "Cashflow CV · payment discipline · employment gaps" },
  { icon: "🤖", label: "Computing risk score",      sub: "Weighted feature scoring 300–900" },
  { icon: "🔍", label: "Generating SHAP reasons",  sub: "Top contributing factors identified" },
  { icon: "🚨", label: "Running fraud checks",      sub: "Income anomaly · stacking · identity plausibility" },
];

export default function ProcessingPage() {
  const [active,   setActive]   = useState(0);
  const [complete, setComplete] = useState([]);

  useEffect(() => {
    if (active >= STAGES.length) return;
    const t = setTimeout(() => {
      setComplete(c => [...c, active]);
      setActive(a => a + 1);
    }, 850);
    return () => clearTimeout(t);
  }, [active]);

  const progress = Math.round((complete.length / STAGES.length) * 100);

  return (
    <div className="dot-grid" style={{ minHeight: "100vh", display: "flex",
      flexDirection: "column", alignItems: "center", justifyContent: "center",
      padding: "48px 24px" }}>

      <div style={{ maxWidth: 560, width: "100%" }}>
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <div style={{ position: "relative", width: 72, height: 72, margin: "0 auto 20px" }}>
            <div style={{ width: 72, height: 72, borderRadius: "50%",
              border: "3px solid var(--border)", position: "absolute" }} />
            <div style={{ width: 72, height: 72, borderRadius: "50%",
              border: "3px solid var(--orange)", position: "absolute",
              borderRightColor: "transparent",
              animation: "spin-slow 1s linear infinite" }} />
            <span style={{ position: "absolute", inset: 0, display: "flex",
              alignItems: "center", justifyContent: "center", fontSize: 28 }}>P</span>
          </div>
          <h1 className="heading" style={{ fontSize: 28, color: "var(--ink)", marginBottom: 6 }}>
            Running Assessment
          </h1>
          <p style={{ color: "var(--muted)", fontSize: 14 }}>
            PRISM pipeline processing your documents
          </p>
        </div>

        {/* Progress bar */}
        <div style={{ background: "var(--border)", borderRadius: 4, height: 4, marginBottom: 32, overflow: "hidden" }}>
          <div style={{ height: "100%", borderRadius: 4, background: "var(--orange)",
            width: `${progress}%`, transition: "width 0.5s ease" }} />
        </div>

        {/* Stage list */}
        <div className="card" style={{ padding: "8px 0" }}>
          {STAGES.map((stage, i) => {
            const isDone   = complete.includes(i);
            const isActive = i === active;
            const isFuture = i > active;
            return (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 16,
                padding: "13px 24px",
                borderBottom: i < STAGES.length - 1 ? "1px solid var(--border)" : "none",
                opacity: isFuture ? 0.35 : 1, transition: "opacity 0.4s, background 0.3s",
                background: isActive ? "#FFF8F5" : "transparent" }}>

                <div style={{ width: 36, height: 36, borderRadius: "50%", flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  background: isDone ? "var(--ink)" : isActive ? "var(--orange)" : "var(--border)",
                  fontSize: isDone ? 14 : 18, transition: "all 0.3s" }}>
                  {isDone ? <span style={{ color: "#fff", fontWeight: 700 }}>✓</span> : stage.icon}
                </div>

                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)", marginBottom: 2 }}>
                    {stage.label}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)" }}>{stage.sub}</div>
                </div>

                <div style={{ fontSize: 12, fontWeight: 500 }}>
                  {isDone   && <span style={{ color: "var(--green)" }}>Done</span>}
                  {isActive && <span style={{ color: "var(--orange)" }}>Running...</span>}
                  {isFuture && <span style={{ color: "var(--muted)" }}>Pending</span>}
                </div>
              </div>
            );
          })}
        </div>

        <div style={{ textAlign: "center", marginTop: 20, fontSize: 13, color: "var(--muted)" }}>
          {progress}% complete · Usually takes under 30 seconds
        </div>
      </div>
    </div>
  );
}