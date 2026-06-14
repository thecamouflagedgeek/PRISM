
import { useState } from "react";
import { Nav } from "../components/Nav";

const BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const TIER_CONFIG = {
  "Low":       { color: "#16A34A", bg: "#F0FDF4", ring: "#86EFAC", label: "Low Risk" },
  "Medium":    { color: "#D97706", bg: "#FFFBEB", ring: "#FCD34D", label: "Medium Risk" },
  "High":      { color: "#DC2626", bg: "#FEF2F2", ring: "#FCA5A5", label: "High Risk" },
  "Very High": { color: "#7C3AED", bg: "#F5F3FF", ring: "#C4B5FD", label: "Very High Risk" },
};

export default function ResultsPage({ go, session, result, setError }) {
  const [whatIf,    setWhatIf]    = useState(null);
  const [overrides, setOverrides] = useState({});
  const [tab,       setTab]       = useState("score");

  const tier   = TIER_CONFIG[result?.risk_tier] || TIER_CONFIG["Medium"];
  const score  = result?.risk_score || 0;
  const pct    = ((score - 300) / 600);
  const circ   = 2 * Math.PI * 80;
  const dash   = circ * (1 - pct);

  const handleWhatIf = async () => {
    try {
      const res = await fetch(`${BASE}/assess/whatif`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Session-ID": session.id },
        body: JSON.stringify({ overrides }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail?.message || "What-if failed");
      setWhatIf(data);
    } catch (e) { setError(e.message); }
  };

  if (!result) return null;
  console.log(result);

  return (
    <div style={{ minHeight: "100vh", background: "var(--cream)" }}>
      <Nav currentPage="results" onLogoClick={() => go("landing")}  onLogout={() => {
    localStorage.clear();
    go("landing");
  }}/>

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "48px 48px 80px" }}>

        {/* ── Page header ── */}
        <div className="fade-up" style={{ marginBottom: 36,
          display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--orange)",
              textTransform: "uppercase", letterSpacing: "0.1em",
              fontFamily: "'Syne', sans-serif", marginBottom: 6 }}>Assessment Complete</div>
            <h1 className="heading" style={{ fontSize: 34, color: "var(--ink)" }}>
              Credit Risk Assessment
            </h1>
            <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 4 }}>
              Borrower: <strong style={{ color: "var(--ink)" }}>{session?.borrowerId}</strong>
              {result.assessed_at && ` · ${new Date(result.assessed_at).toLocaleString("en-IN")}`}
            </div>
          </div>
          <button className="btn-outline" onClick={() => go("login")} style={{ fontSize: 13 }}>
            ← New Assessment
          </button>
        </div>

        {/* ── Score hero ── */}
        <div className="fade-up-1" style={{ background: "var(--white)",
          border: "1px solid var(--border)", borderRadius: 24,
          padding: "36px 40px", marginBottom: 24,
          display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 40,
          alignItems: "center" }}>

          {/* SVG ring */}
          <div style={{ position: "relative", width: 180, height: 180, flexShrink: 0 }}>
            <svg width="180" height="180" viewBox="0 0 180 180">
              <circle cx="90" cy="90" r="80" className="score-ring-track" />
              <circle cx="90" cy="90" r="80" className="score-ring-fill"
                stroke={tier.color}
                strokeDasharray={circ}
                strokeDashoffset={dash} />
            </svg>
            <div style={{ position: "absolute", inset: 0, display: "flex",
              flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
              <div className="display" style={{ fontSize: 40, color: "var(--ink)",
                lineHeight: 1 }}>{score}</div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>/ 900</div>
            </div>
          </div>

          {/* Tier + details */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
              <span className="tier-badge" style={{ background: tier.bg, color: tier.color,
                border: `1px solid ${tier.ring}` }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: tier.color }} />
                {tier.label}
              </span>
              {result.review_required && (
                <span className="tier-badge" style={{ background: "#FFFBEB", color: "#D97706",
                  border: "1px solid #FCD34D" }}>
                  ⚠ Review Required
                </span>
              )}
              {result.data_quality?.thin_file && (
                <span className="tier-badge" style={{ background: "#F5F3FF", color: "#7C3AED",
                  border: "1px solid #C4B5FD" }}>
                  Thin File
                </span>
              )}
            </div>

            <div style={{ fontSize: 14, color: "var(--muted)", lineHeight: 1.7, maxWidth: 400 }}>
              {result.data_quality?.thin_file_note ||
                `Score computed from ${result.data_quality?.feature_coverage}% feature coverage.`}
            </div>

            {/* Score scale bar */}
            <div style={{ marginTop: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between",
                fontSize: 10, color: "var(--muted)", marginBottom: 4 }}>
                <span>300 · Very High</span><span>450 · High</span>
                <span>600 · Medium</span><span>750 · Low</span><span>900</span>
              </div>
              <div style={{ background: "var(--border)", borderRadius: 4, height: 8,
                position: "relative", overflow: "visible" }}>
                <div style={{ position: "absolute", inset: 0, borderRadius: 4,
                  background: "linear-gradient(90deg, #DC2626 0%, #F59E0B 40%, #22C55E 100%)" }} />
                <div style={{ position: "absolute", top: -3, borderRadius: "50%",
                  width: 14, height: 14, background: "var(--ink)",
                  border: "2px solid var(--white)", boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
                  left: `calc(${pct * 100}% - 7px)`, transition: "left 1s ease" }} />
              </div>
            </div>
          </div>

          {/* Confidence */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16,
            padding: "0 0 0 32px", borderLeft: "1px solid var(--border)" }}>
            {[
  {
    label: "Confidence",
    value:
      result.confidence_score != null
        ? `${(result.confidence_score * 100).toFixed(0)}%`
        : "N/A",
  },
  {
    label: "Coverage",
    value:
      result.data_quality?.feature_coverage != null
        ? `${result.data_quality.feature_coverage}%`
        : "N/A",
  },
  {
    label: "Fraud flags",
    value: result.fraud_flags?.length ?? 0,
  },
].map(({ label, value }) => (
              <div key={label}>
                <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500,
                  textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>{label}</div>
                <div className="heading" style={{ fontSize: 22, color: "var(--ink)" }}>{value}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Tab nav ── */}
        <div className="fade-up-2" style={{ display: "flex", gap: 4, marginBottom: 20,
          background: "var(--white)", border: "1px solid var(--border)",
          borderRadius: 12, padding: 4, width: "fit-content" }}>
          {[
            { key: "score",    label: "Why this score" },
            { key: "features",  label: "Features" },
            { key: "fraud",     label: `Fraud flags ${result.fraud_flags?.length ? `(${result.fraud_flags.length})` : ""}` },
            { key: "whatif",    label: "What-if" },
          ].map(({ key, label }) => (
            <button key={key} onClick={() => setTab(key)}
              style={{ padding: "8px 18px", borderRadius: 9, border: "none", cursor: "pointer",
                fontSize: 13, fontWeight: 500, transition: "all 0.15s",
                background: tab === key ? "var(--ink)" : "transparent",
                color: tab === key ? "var(--white)" : "var(--muted)" }}>
              {label}
            </button>
          ))}
        </div>

        {/* ── Tab panels ── */}
        <div className="fade-up-3">

          {/* SHAP reasons */}
          {tab === "score" && (
            <div className="card">
              <div className="heading" style={{ fontSize: 20, marginBottom: 24 }}>Why this score</div>
              {result.shap_reasons?.length > 0 ? result.shap_reasons.map((r, i) => {
                const maxPts = Math.max(...result.shap_reasons.map(x => Math.abs(x.impact_pts)));
                const barW   = Math.abs(r.impact_pts) / maxPts * 100;
                return (
                  <div key={i} style={{ padding: "16px 0",
                    borderBottom: i < result.shap_reasons.length - 1 ? "1px solid var(--border)" : "none" }}>
                    <div style={{ display: "flex", justifyContent: "space-between",
                      alignItems: "center", marginBottom: 8 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div style={{ width: 10, height: 10, borderRadius: "50%", flexShrink: 0,
                          background: r.direction === "positive" ? "var(--green)" : "var(--red)" }} />
                        <span style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)" }}>
                          {r.factor}
                        </span>
                        <span style={{ fontSize: 11, padding: "1px 7px", borderRadius: 50,
                          background: "var(--cream)", color: "var(--muted)",
                          border: "1px solid var(--border)" }}>{r.source}</span>
                      </div>
                      <span style={{ fontSize: 14, fontWeight: 700,
                        fontFamily: "'Syne', sans-serif",
                        color: r.direction === "positive" ? "var(--green)" : "var(--red)" }}>
                        {r.impact_pts > 0 ? "+" : ""}{r.impact_pts} pts
                      </span>
                    </div>
                    <div className="shap-bar-bg">
                      <div className="shap-bar-fill" style={{
                        width: `${barW}%`,
                        background: r.direction === "positive" ? "var(--green)" : "var(--red)"
                      }} />
                    </div>
                  </div>
                );
              }) : (
                <div style={{ color: "var(--muted)", fontSize: 14 }}>No reason codes available.</div>
              )}
            </div>
          )}

          {/* Features */}
          {tab === "features" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {[
                { key: "bank",    label: "Bank Statement Features",  color: "var(--orange)" },
                { key: "salary",  label: "Salary Features",          color: "var(--purple)" },
                { key: "utility", label: "Utility Features",         color: "var(--green)"  },
              ].map(({ key, label, color }) => result.features?.[key] && (
                <div key={key} className="card">
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
                    <div style={{ width: 10, height: 10, borderRadius: "50%", background: color }} />
                    <div className="heading" style={{ fontSize: 16 }}>{label}</div>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 }}>
                    {Object.entries(result.features[key]).map(([k, v]) => (
                      <div key={k} style={{ padding: "12px 14px", borderRadius: 10,
                        background: "var(--cream)", border: "1px solid var(--border)" }}>
                        <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4,
                          fontFamily: "'Syne', sans-serif", textTransform: "uppercase",
                          letterSpacing: "0.05em" }}>{k.replace(/_/g, " ")}</div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "var(--ink)" }}>
                          {v === null || v === undefined ? "—"
                            : typeof v === "boolean" ? (v ? "Yes" : "No")
                            : typeof v === "number" ? (Number.isInteger(v) ? v : Number(v).toFixed(3))
                            : String(v)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Fraud */}
          {tab === "fraud" && (
            <div className="card">
              <div className="heading" style={{ fontSize: 20, marginBottom: 20 }}>Fraud flags</div>
              {result.fraud_flags?.length > 0 ? result.fraud_flags.map((f, i) => (
                <div key={i} style={{ padding: "16px 18px", borderRadius: 12, marginBottom: 10,
                  background: f.severity === "High" ? "#FEF2F2" : "#FFFBEB",
                  border: `1px solid ${f.severity === "High" ? "#FCA5A5" : "#FCD34D"}` }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px",
                      borderRadius: 50, background: f.severity === "High" ? "#DC2626" : "#D97706",
                      color: "#fff" }}>{f.severity}</span>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)" }}>
                      {f.type.replace(/_/g, " ")}
                    </span>
                  </div>
                  <div style={{ fontSize: 13, color: "var(--muted)" }}>{f.detail}</div>
                </div>
              )) : (
                <div style={{ display: "flex", gap: 10, alignItems: "center",
                  color: "var(--green)", fontSize: 15, padding: "8px 0" }}>
                  <span style={{ fontSize: 20 }}>✓</span>
                  No fraud flags detected. Profile appears clean.
                </div>
              )}
            </div>
          )}

          {/* What-if */}
          {tab === "whatif" && (
            <div className="card">
              <div className="heading" style={{ fontSize: 20, marginBottom: 6 }}>What-if Simulation</div>
              <p style={{ color: "var(--muted)", fontSize: 14, marginBottom: 24 }}>
                Override feature values to simulate how your score would change.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16,
                marginBottom: 20 }}>
                {[
                  { key: "cashflow_cv",          label: "Cashflow CV",          type: "number", step: "0.1", min: 0, max: 3, placeholder: "0.00–3.00" },
                  { key: "credit_debit_ratio",   label: "Credit / Debit Ratio", type: "number", step: "0.1", min: 0, max: 5, placeholder: "0.00–5.00" },
                  { key: "net_to_gross_ratio",   label: "Net / Gross Ratio",    type: "number", step: "0.01",min: 0, max: 1, placeholder: "0.00–1.00" },
                  { key: "pf_contribution_flag", label: "PF Contribution",      type: "checkbox" },
                ].map(({ key, label, type, step, min, max, placeholder }) => (
                  <div key={key}>
                    <label style={{ fontSize: 13, fontWeight: 500, color: "var(--ink2)",
                      display: "block", marginBottom: 6 }}>{label}</label>
                    {type === "checkbox" ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <input type="checkbox" style={{ width: 18, height: 18, accentColor: "var(--orange)" }}
                          checked={overrides[key] || false}
                          onChange={e => setOverrides(o => ({ ...o, [key]: e.target.checked }))} />
                        <span style={{ fontSize: 13, color: "var(--muted)" }}>
                          {overrides[key] ? "Yes — PF being deducted" : "No PF contribution"}
                        </span>
                      </div>
                    ) : (
                      <input type="number" step={step} min={min} max={max}
                        placeholder={placeholder}
                        className="input-field"
                        onChange={e => setOverrides(o => ({
                          ...o, [key]: parseFloat(e.target.value) || undefined
                        }))} />
                    )}
                  </div>
                ))}
              </div>

              <button className="btn-primary" onClick={handleWhatIf}
                style={{ background: "var(--orange)", marginBottom: whatIf ? 20 : 0 }}>
                Simulate →
              </button>

              {whatIf && (
                <div style={{ padding: "20px 22px", borderRadius: 14, marginTop: 8,
                  background: whatIf.delta >= 0 ? "#F0FDF4" : "#FEF2F2",
                  border: `1px solid ${whatIf.delta >= 0 ? "#86EFAC" : "#FCA5A5"}` }}>
                  <div style={{ display: "flex", gap: 32, alignItems: "center", flexWrap: "wrap" }}>
                    {[
                      { label: "Base score",  val: whatIf.base_score, color: "var(--ink)" },
                      { label: "→",            val: null, color: "var(--muted)" },
                      { label: "New score",   val: whatIf.new_score,  color: whatIf.delta >= 0 ? "var(--green)" : "var(--red)" },
                      { label: "Change",      val: `${whatIf.delta >= 0 ? "+" : ""}${whatIf.delta} pts`, color: whatIf.delta >= 0 ? "var(--green)" : "var(--red)" },
                    ].map(({ label, val, color }, i) => (
                      <div key={i} style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase",
                          letterSpacing: "0.08em", marginBottom: 4 }}>{label}</div>
                        {val !== null && (
                          <div className="heading" style={{ fontSize: 28, color }}>{val}</div>
                        )}
                      </div>
                    ))}
                    {whatIf.delta_tier && (
                      <div style={{ fontSize: 13, color: "var(--muted)", flex: 1 }}>
                        Tier change: <strong style={{ color: "var(--ink)" }}>{whatIf.delta_tier}</strong>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Warnings ── */}
        {result.warnings?.length > 0 && (
          <div className="fade-up-4" style={{ marginTop: 20, padding: "16px 20px",
            borderRadius: 12, background: "#FFFBEB", border: "1px solid #FCD34D" }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#D97706", marginBottom: 6,
              textTransform: "uppercase", letterSpacing: "0.06em" }}>Data quality notes</div>
            {result.warnings.map((w, i) => (
              <div key={i} style={{ fontSize: 13, color: "#92400E", padding: "2px 0" }}>• {w}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}