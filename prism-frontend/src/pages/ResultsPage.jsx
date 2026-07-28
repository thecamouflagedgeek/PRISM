import { useState, useEffect, useRef } from "react";
const BASE =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

/* ── Mock data for standalone preview ── */
const MOCK_RESULT = {
  risk_score: 634,
  risk_tier: "Medium Risk",
  probability_of_default: 0.087,
  assessed_at: new Date().toISOString(),
  confidence: { confidence_pct: 81.4, components: { document_coverage: 0.87 } },
  fraud_flags: [],
  warnings: ["Utility bills older than 6 months detected — recency may affect score"],
  reason_codes: [
    { factor: "credit_debit_ratio", score_contribution: 42.3, woe: 0.812 },
    { factor: "min_balance",        score_contribution: 28.7, woe: 0.541 },
    { factor: "cashflow_cv",        score_contribution: -18.4, woe: -0.334 },
    { factor: "utility_stability",  score_contribution: 14.2, woe: 0.267 },
    { factor: "net_to_gross_ratio", score_contribution: -6.1, woe: -0.119 },
  ],
  features: {
    bank:    { avg_monthly_credit: 87420, avg_monthly_debit: 41200, credit_debit_ratio: 2.12, cashflow_cv: 0.68, min_balance_l3m: 18400, num_emi_transactions: 3 },
    salary:  { gross_salary: 95000, net_salary: 81200, net_to_gross_ratio: 0.854, pf_deducted: true, num_salary_credits: 3 },
    utility: { avg_bill_amount: 2840, bills_on_time: 5, bills_total: 6, utility_stability: 0.833 },
  },
};
const MOCK_SESSION = { id: "sess_demo", borrowerId: "BRRW-4821" };

/* ── Design tokens (reference image: dot-grid, airy, white cards, coral/purple) ── */
const T = {
  bg:         "#F6F6F8",
  white:      "#FFFFFF",
  ink:        "#18181B",
  muted:      "#71717A",
  border:     "#E4E4E7",
  coral:      "#FF5C3A",
  purple:     "#7C3AED",
  green:      "#16A34A",
  amber:      "#D97706",
  red:        "#DC2626",
  blue:       "#2563EB",
  softBlue:   "#EFF6FF",
  softCoral:  "#FFF5F3",
  softGreen:  "#F0FDF4",
  softAmber:  "#FFFBEB",
  softPurple: "#F5F3FF",
  softRed:    "#FEF2F2",
};

const TIER_CONFIG = {
  "Low Risk":       { color: T.green,  soft: T.softGreen,  label: "Low Risk",       scoreLabel: "Excellent" },
  "Medium Risk":    { color: T.amber,  soft: T.softAmber,  label: "Medium Risk",    scoreLabel: "Fair"      },
  "High Risk":      { color: T.red,    soft: T.softRed,    label: "High Risk",      scoreLabel: "Poor"      },
  "Very High Risk": { color: T.purple, soft: T.softPurple, label: "Very High Risk", scoreLabel: "Critical"  },
};

/* ── Dot-grid background ── */
const DOT_BG = {
  backgroundImage: `radial-gradient(circle, #D1D1DB 1.2px, transparent 1.2px)`,
  backgroundSize: "30px 30px",
  backgroundColor: T.bg,
};

/* ── Shared primitives ── */
const Card = ({ children, style = {} }) => (
  <div style={{
    background: T.white, border: `1px solid ${T.border}`,
    borderRadius: 20, padding: "28px 32px",
    boxShadow: "0 1px 12px rgba(0,0,0,0.05)", ...style,
  }}>{children}</div>
);

const Eyebrow = ({ children, color = T.coral }) => (
  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.13em",
    textTransform: "uppercase", color, marginBottom: 6 }}>
    {children}
  </div>
);

const Badge = ({ children, color, bg }) => (
  <span style={{
    display: "inline-flex", alignItems: "center", gap: 6,
    padding: "5px 14px", borderRadius: 100, background: bg,
    color, fontSize: 12, fontWeight: 700, letterSpacing: "0.04em",
  }}>
    <span style={{ width: 6, height: 6, borderRadius: "50%", background: color, flexShrink: 0 }} />
    {children}
  </span>
);

/* ── Arc gauge ── */
const ArcGauge = ({ score, color }) => {
  const pct = (score - 300) / 600;
  const R = 68; const cx = 84; const cy = 84;
  const start = Math.PI * 0.78; const end = Math.PI * 2.22;
  const span = end - start;
  const pt = (a) => [cx + R * Math.cos(a), cy + R * Math.sin(a)];
  const arc = (from, to, r) => {
    const [x1,y1] = pt(from); const [x2,y2] = pt(to);
    return `M ${x1} ${y1} A ${r} ${r} 0 ${(to-from)>Math.PI?1:0} 1 ${x2} ${y2}`;
  };
  return (
    <svg width="168" height="120" viewBox="0 0 168 120">
      <path d={arc(start, end, R)} fill="none" stroke={T.border} strokeWidth="11" strokeLinecap="round"/>
      <path d={arc(start, start + span * pct, R)} fill="none" stroke={color} strokeWidth="11" strokeLinecap="round"/>
      <text x="84" y="82" textAnchor="middle" style={{ fontSize: 34, fontWeight: 800, fill: T.ink, fontFamily: "inherit" }}>{score}</text>
      <text x="84" y="100" textAnchor="middle" style={{ fontSize: 11, fill: T.muted, fontFamily: "inherit" }}>out of 900</text>
    </svg>
  );
};

/* ── Stat chip ── */
const StatChip = ({ label, value, color = T.ink }) => (
  <div style={{ background: T.bg, borderRadius: 14, padding: "16px 18px", border: `1px solid ${T.border}`, flex: 1 }}>
    <div style={{ fontSize: 10, fontWeight: 700, color: T.muted, textTransform: "uppercase",
      letterSpacing: "0.1em", marginBottom: 6 }}>{label}</div>
    <div style={{ fontSize: 22, fontWeight: 800, color }}>{value}</div>
  </div>
);

/* ═══════════════════════════════════════
   SCORE HERO
═══════════════════════════════════════ */
const ScoreHero = ({ result, tier, score }) => (
  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 20, marginBottom: 28 }}>
    {/* Main card */}
    <Card style={{ gridColumn: "1 / 3", padding: "36px 40px" }}>
      <div style={{ display: "flex", gap: 40, alignItems: "center" }}>
        <div style={{ flexShrink: 0 }}>
          <ArcGauge score={score} color={tier.color} />
        </div>
        <div style={{ flex: 1 }}>
          <Eyebrow>Credit risk assessment</Eyebrow>
          <h2 style={{ fontSize: 26, fontWeight: 800, color: T.ink, margin: "8px 0 12px", lineHeight: 1.25 }}>
            {tier.scoreLabel} Credit Profile
          </h2>
          <Badge color={tier.color} bg={tier.soft}>{tier.label}</Badge>

          {/* Gradient scale bar */}
          <div style={{ marginTop: 22 }}>
            <div style={{ display: "flex", justifyContent: "space-between",
              fontSize: 10, color: T.muted, marginBottom: 5, fontWeight: 600 }}>
              {["300","450","600","750","900"].map(v => <span key={v}>{v}</span>)}
            </div>
            <div style={{ position: "relative", height: 7, borderRadius: 100,
              background: `linear-gradient(90deg, ${T.red}, ${T.amber} 40%, ${T.green})` }}>
              <div style={{
                position: "absolute", top: "50%",
                left: `${((score - 300) / 600) * 100}%`,
                transform: "translate(-50%, -50%)",
                width: 16, height: 16, borderRadius: "50%",
                background: T.white, border: `3px solid ${tier.color}`,
                boxShadow: `0 2px 8px ${tier.color}55`,
              }} />
            </div>
          </div>

          <div style={{ marginTop: 14, fontSize: 12, color: T.muted, lineHeight: 1.7 }}>
            Based on{" "}
            <strong style={{ color: T.ink }}>
              {result.confidence?.components?.document_coverage != null
                ? `${(result.confidence.components.document_coverage * 100).toFixed(0)}% document coverage`
                : "N/A"}
            </strong>{" "}
            · Assessed {result.assessed_at ? new Date(result.assessed_at).toLocaleString("en-IN") : ""}
          </div>
        </div>
      </div>
    </Card>

    {/* Stats column */}
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <StatChip label="Probability of default"
        value={result.probability_of_default != null ? `${(result.probability_of_default * 100).toFixed(1)}%` : "—"}
        color={tier.color} />
      <StatChip label="Model confidence"
        value={result.confidence?.confidence_pct != null ? `${result.confidence.confidence_pct.toFixed(1)}%` : "—"}
        color={T.purple} />
      <StatChip label="Fraud flags"
        value={result.fraud_flags?.length ?? 0}
        color={result.fraud_flags?.length ? T.red : T.green} />
    </div>
  </div>
);

/* ═══════════════════════════════════════
   TAB BAR
═══════════════════════════════════════ */
const TABS = [
  { key: "score",    label: "Score breakdown" },
  { key: "features", label: "Data features"   },
  { key: "improve",  label: "How to improve"  },
  { key: "learn",    label: "Credit 101"      },
  { key: "fraud",    label: "Fraud check"     },
  { key: "whatif",   label: "What-if"         },
];

const TabBar = ({ active, onChange }) => (
  <div style={{ display: "flex", gap: 3, marginBottom: 28, background: T.white,
    border: `1px solid ${T.border}`, borderRadius: 100, padding: 5,
    width: "fit-content", boxShadow: "0 2px 8px rgba(0,0,0,0.04)" }}>
    {TABS.map(({ key, label }) => (
      <button key={key} onClick={() => onChange(key)} style={{
        padding: "9px 20px", borderRadius: 100, border: "none", cursor: "pointer",
        fontSize: 13, fontWeight: 600, transition: "all 0.15s",
        background: active === key ? T.ink : "transparent",
        color: active === key ? T.white : T.muted,
      }}>
        {label}
      </button>
    ))}
  </div>
);

/* ═══════════════════════════════════════
   SCORE BREAKDOWN + SHAP EXPLAINABILITY SIDEBAR
═══════════════════════════════════════ */
const FACTOR_META = {
  credit_debit_ratio: { icon: "💳", label: "Credit / Debit Ratio",  desc: "How much you receive vs. spend" },
  cashflow_cv:        { icon: "📊", label: "Cashflow Stability",     desc: "Consistency of monthly cash flow" },
  net_to_gross_ratio: { icon: "💼", label: "Net / Gross Salary",     desc: "Take-home pay relative to gross" },
  utility_stability:  { icon: "⚡", label: "Utility Bill Stability", desc: "Regularity of utility payments"  },
  min_balance:        { icon: "🏦", label: "Minimum Balance",        desc: "Lowest balance in last 3 months" },
};

/* ── Pie chart primitive (pure SVG, no external chart lib needed) ── */
const PieChart = ({ slices, size = 180 }) => {
  const total = slices.reduce((s, x) => s + x.value, 0);
  if (total <= 0) return null;
  const R = size / 2;
  const cx = R, cy = R;
  let angle = -Math.PI / 2; // start at 12 o'clock

  const paths = slices.map((s, i) => {
    const frac = s.value / total;
    const sweep = frac * 2 * Math.PI;
    const x1 = cx + R * Math.cos(angle);
    const y1 = cy + R * Math.sin(angle);
    const endAngle = angle + sweep;
    const x2 = cx + R * Math.cos(endAngle);
    const y2 = cy + R * Math.sin(endAngle);
    const largeArc = sweep > Math.PI ? 1 : 0;
    const d = `M ${cx} ${cy} L ${x1} ${y1} A ${R} ${R} 0 ${largeArc} 1 ${x2} ${y2} Z`;
    angle = endAngle;
    return <path key={i} d={d} fill={s.color} stroke="#fff" strokeWidth="2" />;
  });

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {paths}
      <circle cx={cx} cy={cy} r={R * 0.55} fill={T.white} />
      <text x={cx} y={cy - 6} textAnchor="middle" style={{ fontSize: 20, fontWeight: 800, fill: T.ink }}>
        {slices.length}
      </text>
      <text x={cx} y={cy + 13} textAnchor="middle" style={{ fontSize: 10, fill: T.muted }}>
        factors
      </text>
    </svg>
  );
};

const PIE_COLORS = [T.coral, T.purple, T.blue, T.green, T.amber];

const ContributionPieCard = ({ reason_codes }) => {
  const slices = reason_codes.map((r, i) => ({
    key: r.factor,
    value: Math.abs(r.score_contribution ?? 0),
    signed: r.score_contribution ?? 0,
    color: PIE_COLORS[i % PIE_COLORS.length],
  }));
  const total = slices.reduce((s, x) => s + x.value, 0);

  return (
    <Card>
      <Eyebrow>Impact by factor</Eyebrow>
      <h3 style={{ fontSize: 15, fontWeight: 800, color: T.ink, marginBottom: 14 }}>
        Where your score points came from
      </h3>
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div style={{ flexShrink: 0 }}>
          <PieChart slices={slices} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, flex: 1 }}>
          {slices.map((s, i) => {
            const fm = FACTOR_META[s.key] || { label: s.key };
            const pct = total > 0 ? Math.round((s.value / total) * 100) : 0;
            const isPos = s.signed >= 0;
            return (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: s.color, flexShrink: 0 }} />
                <span style={{ fontSize: 12, color: T.ink, fontWeight: 600, flex: 1 }}>{fm.label}</span>
                <span style={{ fontSize: 12, fontWeight: 800, color: isPos ? T.green : T.red }}>
                  {isPos ? "+" : ""}{s.signed.toFixed(1)}
                </span>
                <span style={{ fontSize: 11, color: T.muted, width: 32, textAlign: "right" }}>{pct}%</span>
              </div>
            );
          })}
        </div>
      </div>
      <p style={{ fontSize: 12, color: T.muted, lineHeight: 1.6, marginTop: 16 }}>
        Slice size shows how much each factor swayed your score, regardless of direction.
        Check the sign next to each factor to see whether it helped (green) or hurt (red) your final number.
      </p>
    </Card>
  );
};

const ScorePanel = ({ result }) => {
  const reason_codes = result?.reason_codes;
  const meta = result?.model_metadata || {};
  const logOdds = result?.log_odds;
  const pd = result?.probability_of_default;

  if (!reason_codes?.length) return <Card><div style={{ color: T.muted }}>No reason codes available.</div></Card>;
  const maxAbs = Math.max(...reason_codes.map(r => Math.abs(r.score_contribution ?? 0)));

  // Reconstruct the base log-odds component (φ₀) so the sidebar ledger sums to the
  // actual score: total log-odds minus the sum of all shown contributions, rescaled
  // back into score points via the same PDO factor used by the backend.
  const factor = meta.factor ?? 72.13;
  const sumContribPts = reason_codes.reduce((s, r) => s + (r.score_contribution ?? 0), 0);
  const baseLogOddsPts = logOdds != null ? -factor * logOdds - sumContribPts : null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 20, alignItems: "start" }}>

      {/* ── LEFT: factor list ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <Card>
          <Eyebrow>Model explainability · WoE logistic scorecard</Eyebrow>
          <h3 style={{ fontSize: 20, fontWeight: 800, color: T.ink, marginBottom: 6 }}>Score breakdown</h3>
          <p style={{ fontSize: 13, color: T.muted, marginBottom: 24, lineHeight: 1.7 }}>
            Each factor either added or subtracted points from your final score.
            Green bars helped your profile; red bars pulled it down.
          </p>
          {reason_codes.map((r, i) => {
            const contrib = r.score_contribution ?? 0;
            const isPos = contrib >= 0;
            const barPct = maxAbs > 0 ? (Math.abs(contrib) / maxAbs) * 100 : 0;
            const fm = FACTOR_META[r.factor] || { icon: "📌", label: r.factor, desc: "" };
            return (
              <div key={i} style={{ padding: "20px 0", borderBottom: i < reason_codes.length-1 ? `1px solid ${T.border}` : "none" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
                  <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
                    <div style={{ width: 42, height: 42, borderRadius: 12, fontSize: 18,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      background: isPos ? T.softGreen : T.softRed, flexShrink: 0 }}>
                      {fm.icon}
                    </div>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 700, color: T.ink }}>{fm.label}</div>
                      <div style={{ fontSize: 12, color: T.muted }}>{fm.desc}</div>
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 20, fontWeight: 800, color: isPos ? T.green : T.red }}>
                      {contrib > 0 ? "+" : ""}{contrib.toFixed(1)} pts
                    </div>
                    <div style={{ fontSize: 11, color: T.muted }}>WoE {r.woe?.toFixed(3) ?? "—"}</div>
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ flex: 1, height: 7, borderRadius: 100, background: T.bg, overflow: "hidden" }}>
                    <div style={{ width: `${barPct}%`, height: "100%", borderRadius: 100,
                      background: isPos ? T.green : T.red, transition: "width 0.8s ease" }} />
                  </div>
                  <Badge color={isPos ? T.green : T.red} bg={isPos ? T.softGreen : T.softRed}>
                    {isPos ? "Positive" : "Negative"}
                  </Badge>
                </div>
              </div>
            );
          })}
        </Card>

        {/* Methodology card */}
        <Card style={{ background: T.softBlue, border: `1px solid #BFDBFE` }}>
          <div style={{ display: "flex", gap: 18, alignItems: "flex-start" }}>
            <div style={{ fontSize: 30, flexShrink: 0 }}>🔬</div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: T.ink, marginBottom: 6 }}>How PRISM calculates your score</div>
              <div style={{ fontSize: 13, color: "#1E40AF", lineHeight: 1.7 }}>
                PRISM uses a <strong>Weight of Evidence (WoE) Logistic Scorecard</strong> — the same methodology used by Indian banks and NBFCs.
                Each feature is binned into risk bands, assigned a WoE value based on default rates, then multiplied by a logistic regression
                coefficient. The final log-odds are converted to a 300–900 score using PDO scaling ({meta.pdo ?? 50} points to double the odds, anchored at {meta.base_score ?? 600}).
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* ── RIGHT: explainability sidebar ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16, position: "sticky", top: 80 }}>
        <ContributionPieCard reason_codes={reason_codes} />

        <Card>
          <Eyebrow>Step-by-step</Eyebrow>
          <h3 style={{ fontSize: 15, fontWeight: 800, color: T.ink, marginBottom: 14 }}>Walking through your score</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {[
              { n: 1, text: "Each raw value (e.g. your credit-debit ratio) is placed into a risk bin, and converted to a Weight of Evidence (WoE) number." },
              { n: 2, text: "Each WoE value is compared to the population average for that same feature — the difference is what actually moves your score." },
              { n: 3, text: "That difference is multiplied by the model's learned coefficient (βᵢ) for the feature, giving its exact contribution in log-odds." },
              { n: 4, text: "All contributions plus a base rate are summed into total log-odds, then linearly rescaled into your 300–900 score." },
            ].map(({ n, text }) => (
              <div key={n} style={{ display: "flex", gap: 10 }}>
                <div style={{ width: 22, height: 22, borderRadius: "50%", flexShrink: 0, background: T.softPurple,
                  color: T.purple, fontSize: 11, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  {n}
                </div>
                <div style={{ fontSize: 12.5, color: "#374151", lineHeight: 1.6 }}>{text}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <Eyebrow>The math, using your numbers</Eyebrow>
          <h3 style={{ fontSize: 15, fontWeight: 800, color: T.ink, marginBottom: 12 }}>Your contribution ledger</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
            {reason_codes.map((r, i) => {
              const fm = FACTOR_META[r.factor] || { label: r.factor };
              return (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                  fontSize: 12, padding: "8px 10px", borderRadius: 8, background: T.bg }}>
                  <span style={{ color: T.muted, fontWeight: 600 }}>{fm.label}</span>
                  <span style={{ fontWeight: 800, color: r.score_contribution >= 0 ? T.green : T.red }}>
                    {r.score_contribution >= 0 ? "+" : ""}{r.score_contribution.toFixed(1)}
                  </span>
                </div>
              );
            })}
            {baseLogOddsPts != null && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                fontSize: 12, padding: "8px 10px", borderRadius: 8, background: T.softAmber }}>
                <span style={{ color: "#92400E", fontWeight: 700 }}>Base rate (φ₀)</span>
                <span style={{ fontWeight: 800, color: "#92400E" }}>
                  {baseLogOddsPts >= 0 ? "+" : ""}{baseLogOddsPts.toFixed(1)}
                </span>
              </div>
            )}
          </div>
          <div style={{ borderTop: `1px dashed ${T.border}`, paddingTop: 10, display: "flex",
            justifyContent: "space-between", fontSize: 13 }}>
            <span style={{ fontWeight: 700, color: T.ink }}>Final score</span>
            <span style={{ fontWeight: 800, color: T.ink }}>{result?.risk_score}</span>
          </div>
          {logOdds != null && (
            <div style={{ fontSize: 11, color: T.muted, marginTop: 8, lineHeight: 1.6 }}>
              Total log-odds: <strong>{logOdds.toFixed(4)}</strong> · Probability of default: <strong>{(pd * 100).toFixed(1)}%</strong>
            </div>
          )}
        </Card>

        <Card style={{ background: T.softGreen, border: "1px solid #BBF7D0" }}>
          <div style={{ fontSize: 12, color: "#166534", lineHeight: 1.65 }}>
            <strong>Why this matters:</strong> under ECOA / RBI Fair Practices Code, any adverse
            credit decision must come with specific, traceable reasons — not just a number.
            This breakdown is exact, not estimated, because the scorecard is linear.
          </div>
        </Card>
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════
   DATA FEATURES
═══════════════════════════════════════ */
const FeaturesPanel = ({ features }) => {
  const groups = [
    { key: "bank",    label: "Bank statement features",  icon: "🏦", accent: T.coral  },
    { key: "salary",  label: "Salary slip features",     icon: "💼", accent: T.purple },
    { key: "utility", label: "Utility bill features",    icon: "⚡", accent: T.blue   },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {groups.map(({ key, label, icon, accent }) => {
        const data = features?.[key];
        if (!data) return null;
        return (
          <Card key={key}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, fontSize: 18,
                display: "flex", alignItems: "center", justifyContent: "center",
                background: accent + "18" }}>{icon}</div>
              <Eyebrow color={accent}>{label}</Eyebrow>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))", gap: 12 }}>
              {Object.entries(data).map(([k, v]) => (
                <div key={k} style={{ padding: "14px 16px", borderRadius: 14, background: T.bg, border: `1px solid ${T.border}` }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: T.muted, textTransform: "uppercase",
                    letterSpacing: "0.1em", marginBottom: 6 }}>{k.replace(/_/g, " ")}</div>
                  <div style={{ fontSize: 18, fontWeight: 800, color: T.ink }}>
                    {v === null || v === undefined ? "—"
                      : typeof v === "boolean" ? (v ? "Yes" : "No")
                      : typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString("en-IN") : Number(v).toFixed(3))
                      : String(v)}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        );
      })}
    </div>
  );
};

/* ═══════════════════════════════════════
   HOW TO IMPROVE
═══════════════════════════════════════ */
const SCORE_BANDS = [
  { range: "750–900", lo: 750, hi: 900, label: "Excellent", color: T.green,  desc: "Best loan rates, instant approval from most lenders." },
  { range: "600–749", lo: 600, hi: 749, label: "Good",      color: T.blue,   desc: "Good credit health. Small improvements unlock premium products." },
  { range: "450–599", lo: 450, hi: 599, label: "Fair",      color: T.amber,  desc: "Borderline. Focus on cashflow stability and minimum balance." },
  { range: "300–449", lo: 300, hi: 449, label: "Poor",      color: T.red,    desc: "High risk. Systematic improvements needed over 3–6 months." },
];

const TIPS = [
  {
    icon: "💳", title: "Improve your credit-debit ratio", target: "Target: > 2.0",
    accent: T.coral, soft: T.softCoral, impact: "High impact · +50–120 pts",
    tips: [
      "Reduce discretionary spending — track monthly outflows and identify non-essential categories.",
      "Consolidate debt payments to reduce the number of debit transactions.",
      "Avoid month-end overdrafts — they create DR entries that worsen the ratio.",
      "Ensure all income (salary, freelance, transfers) is credited to the same primary account.",
    ],
  },
  {
    icon: "📊", title: "Stabilise your monthly cashflow", target: "Target: CV < 0.5",
    accent: T.purple, soft: T.softPurple, impact: "High impact · +30–80 pts",
    tips: [
      "Maintain regular income deposits — salary credited on the same date each month signals stability.",
      "Set up SIPs or recurring transfers to smooth out erratic outflows.",
      "Avoid large one-off credits that inflate variance; document them separately.",
      "A 6-month statement with low variance carries significantly more weight than 3 months.",
    ],
  },
  {
    icon: "🏦", title: "Maintain a healthy minimum balance", target: "Target: > ₹15,000",
    accent: T.blue, soft: T.softBlue, impact: "High impact · +60–100 pts",
    tips: [
      "Keep a minimum buffer of ₹15,000–₹20,000 in your primary account at all times.",
      "Set a low-balance alert at ₹20,000 in your banking app.",
      "Maintain a separate emergency fund to prevent drawing down your main account.",
      "If you have multiple accounts, consolidate to one showing consistent positive balances.",
    ],
  },
  {
    icon: "⚡", title: "Pay utility bills on time", target: "Target: stability > 0.8",
    accent: T.green, soft: T.softGreen, impact: "Moderate impact · +20–60 pts",
    tips: [
      "Set up auto-pay for electricity, water, and gas — even one missed payment signals risk.",
      "Pay before the due date, not on it — payment timestamps matter.",
      "Keep utility bills from the last 6 months accessible as PDFs for faster assessment.",
      "Register mobile alerts with MSEDCL / BSES for upcoming due dates.",
    ],
  },
  {
    icon: "💼", title: "Maximise net-to-gross salary ratio", target: "Target: ratio > 0.82",
    accent: "#B45309", soft: T.softAmber, impact: "Moderate impact · +10–30 pts",
    tips: [
      "Ensure PF, professional tax, and TDS appear correctly on your payslip.",
      "A net/gross ratio above 0.82 places you in the best scoring bin.",
      "Structured salary with clear HRA, basic, and allowance breakdowns scores better than a lump-sum.",
      "Check whether voluntary deductions (NPS, insurance) are unnecessarily inflating total deductions.",
    ],
  },
];

const ImprovePanel = ({ result }) => {
  const score = result?.risk_score ?? 0;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* Where you stand */}
      <Card>
        <Eyebrow>Score reference</Eyebrow>
        <h3 style={{ fontSize: 20, fontWeight: 800, color: T.ink, marginBottom: 18 }}>Where you stand on the PRISM scale</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
          {SCORE_BANDS.map(({ range, lo, hi, label, color, desc }) => {
            const isActive = score >= lo && score <= hi;
            return (
              <div key={range} style={{ padding: "18px 16px", borderRadius: 16, position: "relative",
                border: `2px solid ${isActive ? color : T.border}`,
                background: isActive ? color + "0F" : T.bg }}>
                {isActive && (
                  <div style={{ position: "absolute", top: -11, right: 12,
                    background: color, color: "#fff", fontSize: 9, fontWeight: 800,
                    padding: "3px 10px", borderRadius: 100, letterSpacing: "0.08em" }}>
                    YOU ARE HERE
                  </div>
                )}
                <div style={{ fontSize: 16, fontWeight: 800, color, marginBottom: 4 }}>{range}</div>
                <div style={{ fontSize: 13, fontWeight: 700, color: T.ink, marginBottom: 8 }}>{label}</div>
                <div style={{ fontSize: 12, color: T.muted, lineHeight: 1.6 }}>{desc}</div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Tip cards */}
      {TIPS.map((tip, i) => (
        <Card key={i}>
          <div style={{ display: "flex", gap: 16, alignItems: "flex-start", marginBottom: 18 }}>
            <div style={{ width: 48, height: 48, borderRadius: 14, fontSize: 22, flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center", background: tip.soft }}>
              {tip.icon}
            </div>
            <div style={{ flex: 1, display: "flex", justifyContent: "space-between",
              alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 800, color: T.ink }}>{tip.title}</div>
                <div style={{ fontSize: 12, color: tip.accent, fontWeight: 600, marginTop: 3 }}>{tip.target}</div>
              </div>
              <span style={{ fontSize: 11, padding: "5px 12px", borderRadius: 100,
                background: tip.soft, color: tip.accent, fontWeight: 700 }}>{tip.impact}</span>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 10 }}>
            {tip.tips.map((t, j) => (
              <div key={j} style={{ display: "flex", gap: 10, alignItems: "flex-start",
                padding: "12px 14px", borderRadius: 12, background: T.bg, border: `1px solid ${T.border}` }}>
                <div style={{ width: 22, height: 22, borderRadius: 6, flexShrink: 0,
                  background: tip.soft, color: tip.accent,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 11, fontWeight: 800 }}>{j+1}</div>
                <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.65 }}>{t}</div>
              </div>
            ))}
          </div>
        </Card>
      ))}

      {/* Action footer */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
        {[
          { icon: "🎯", title: "Set a 90-day goal", body: "Pick your two lowest-scoring factors and make targeted changes. Re-submit after 90 days to track improvement." },
          { icon: "📱", title: "Use Account Aggregator", body: "Connect your bank via NBFC-AA framework for real-time, consent-based assessment with richer data." },
          { icon: "🔒", title: "Your data is safe", body: "PRISM is DPDPA 2023 compliant. Documents are processed in-memory and never stored without explicit consent." },
        ].map(({ icon, title, body }) => (
          <Card key={title} style={{ background: T.ink, border: "none" }}>
            <div style={{ fontSize: 26, marginBottom: 12 }}>{icon}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#FFFFFF", marginBottom: 8 }}>{title}</div>
            <div style={{ fontSize: 12, color: "#A1A1AA", lineHeight: 1.7 }}>{body}</div>
          </Card>
        ))}
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════
   CREDIT 101  (new financial education tab)
═══════════════════════════════════════ */
const Credit101Panel = () => {
  const concepts = [
    {
      icon: "📘", title: "What is a credit score?", accent: T.blue,
      body: "A credit score is a three-digit number (300–900 in PRISM's scale) that summarises how likely you are to repay a loan on time. Lenders use it as a quick proxy for risk — the higher your score, the better interest rates and loan amounts you qualify for.",
      bullets: [
        "Scores above 750 unlock the best home loan and personal loan rates.",
        "A score of 600–749 still qualifies for most products, but at higher interest.",
        "Scores below 600 may require collateral, a co-applicant, or a smaller loan amount.",
        "Unlike CIBIL which looks at credit history, PRISM focuses on your cash flow behaviour.",
      ],
    },
    {
      icon: "⚖️", title: "What is Probability of Default (PD)?", accent: T.purple,
      body: "The PD is the statistical likelihood that a borrower will miss repayments within the next 12 months. PRISM's model is trained on millions of Indian bank statement samples to estimate this probability from your transaction behaviour alone — no credit bureau pull required.",
      bullets: [
        "A PD below 5% is considered excellent and qualifies for the lowest-risk tier.",
        "A PD between 5–15% is medium risk — most borrowers fall here.",
        "Above 20% PD, lenders typically apply stricter conditions or decline.",
        "Your PD improves as you demonstrate consistent income and controlled spending over time.",
      ],
    },
    {
      icon: "🔢", title: "Weight of Evidence (WoE) scoring", accent: T.coral,
      body: "WoE is a statistical technique that converts each financial metric into a standardised risk signal. PRISM bins your data (e.g. credit-debit ratios of 0–1, 1–2, 2–3, 3+) and computes the log-odds of default in each bin. Higher WoE = lower default rate in that bin.",
      bullets: [
        "WoE values are positive when a bin has fewer defaults than average.",
        "WoE values are negative when a bin has more defaults than average.",
        "Each WoE value is multiplied by a regression weight to get score contribution.",
        "This makes PRISM scores fully explainable — every point can be traced to a factor.",
      ],
    },
    {
      icon: "💰", title: "The credit-debit ratio explained", accent: T.green,
      body: "Your credit-debit ratio compares total money flowing into your account (credits) versus total money leaving (debits) in a month. A ratio above 2.0 means you receive at least twice what you spend — a strong signal of financial surplus.",
      bullets: [
        "Ratio < 1.0: spending exceeds income — very high risk signal.",
        "Ratio 1.0–1.5: just covering expenses — borderline.",
        "Ratio 1.5–2.0: comfortable surplus — medium risk.",
        "Ratio > 2.0: strong surplus — best scoring bin.",
      ],
    },
    {
      icon: "📉", title: "Cashflow CV and what it means", accent: T.amber,
      body: "Coefficient of Variation (CV) measures how erratic your monthly cash flow is. A low CV (< 0.5) means your income and spending are stable and predictable — the ideal borrower profile. High CV suggests volatile finances, which increases perceived risk.",
      bullets: [
        "CV < 0.3: very stable — best scoring bin.",
        "CV 0.3–0.6: some variability but acceptable.",
        "CV 0.6–1.0: high variability — red flag for lenders.",
        "CV > 1.0: very erratic — significant negative impact on score.",
      ],
    },
    {
      icon: "🏛️", title: "How Indian banks assess creditworthiness", accent: "#0E7490",
      body: "Traditional bank credit assessment in India relies heavily on CIBIL scores, ITRs, and salary slips. PRISM's alternative data approach — using bank statements and utility bills — is aligned with RBI's Account Aggregator (AA) framework, enabling credit access for the 200M+ Indians who are credit-invisible.",
      bullets: [
        "Account Aggregator (AA) enables consent-based bank data sharing with lenders.",
        "RBI's 2021 circular mandated all banks to participate in the AA ecosystem.",
        "Alternative credit scoring helps thin-file borrowers who lack CIBIL history.",
        "PRISM scores are designed to complement (not replace) bureau-based scoring.",
      ],
    },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Hero intro */}
      <Card style={{ background: `linear-gradient(135deg, ${T.ink} 0%, #2D2B55 100%)`, border: "none" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 40, alignItems: "center" }}>
          <div>
            <Eyebrow color={T.coral}>Financial literacy</Eyebrow>
            <h2 style={{ fontSize: 24, fontWeight: 800, color: "#FFFFFF", margin: "10px 0 14px", lineHeight: 1.3 }}>
              Understand exactly what drives your score
            </h2>
            <p style={{ fontSize: 13, color: "#A1A1AA", lineHeight: 1.8 }}>
              The more you understand how PRISM scores are calculated, the more control you have over improving them.
              This guide covers the key concepts behind every number on your report.
            </p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {[
              { label: "Core factors", val: "5" },
              { label: "Score range", val: "600" },
              { label: "WoE bins used", val: "24" },
              { label: "Data points", val: "100+" },
            ].map(({ label, val }) => (
              <div key={label} style={{ background: "rgba(255,255,255,0.07)", borderRadius: 14,
                padding: "14px 16px", border: "1px solid rgba(255,255,255,0.1)" }}>
                <div style={{ fontSize: 24, fontWeight: 800, color: T.coral }}>{val}</div>
                <div style={{ fontSize: 11, color: "#A1A1AA", marginTop: 4, fontWeight: 600,
                  textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Concept cards */}
      {concepts.map((c, i) => (
        <Card key={i}>
          <div style={{ display: "flex", gap: 16, alignItems: "flex-start", marginBottom: 16 }}>
            <div style={{ width: 46, height: 46, borderRadius: 14, fontSize: 20, flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              background: c.accent + "18" }}>{c.icon}</div>
            <div>
              <Eyebrow color={c.accent}>Credit 101</Eyebrow>
              <h3 style={{ fontSize: 17, fontWeight: 800, color: T.ink, marginTop: 2 }}>{c.title}</h3>
            </div>
          </div>
          <p style={{ fontSize: 13, color: "#374151", lineHeight: 1.75, marginBottom: 18 }}>{c.body}</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
            {c.bullets.map((b, j) => (
              <div key={j} style={{ display: "flex", gap: 10, alignItems: "flex-start",
                padding: "11px 14px", borderRadius: 12, background: T.bg, border: `1px solid ${T.border}` }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: c.accent,
                  flexShrink: 0, marginTop: 5 }} />
                <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.6 }}>{b}</div>
              </div>
            ))}
          </div>
        </Card>
      ))}

      {/* Glossary */}
      <Card>
        <Eyebrow>Quick reference glossary</Eyebrow>
        <h3 style={{ fontSize: 18, fontWeight: 800, color: T.ink, marginBottom: 16 }}>Key terms</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
          {[
            { term: "PDO", def: "Points to Double Odds — the number of score points that halve the odds of default. PRISM uses PDO = 50." },
            { term: "Log-odds", def: "The natural log of the ratio of default probability to non-default probability. The raw output of the logistic regression." },
            { term: "WoE", def: "Weight of Evidence — log ratio of Distribution of Events to Distribution of Non-Events in a bin." },
            { term: "IV", def: "Information Value — measures a feature's predictive power. IV > 0.3 indicates a strong predictor." },
            { term: "DPDPA 2023", def: "Digital Personal Data Protection Act — India's primary data privacy law governing how financial data may be stored and processed." },
            { term: "NBFC-AA", def: "Non-Banking Financial Company — Account Aggregator. Licensed entities that facilitate consent-based financial data sharing between providers and users." },
          ].map(({ term, def }) => (
            <div key={term} style={{ padding: "14px 16px", borderRadius: 14,
              background: T.bg, border: `1px solid ${T.border}` }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: T.ink, marginBottom: 6 }}>{term}</div>
              <div style={{ fontSize: 12, color: T.muted, lineHeight: 1.65 }}>{def}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};

/* ═══════════════════════════════════════
   FRAUD CHECK
═══════════════════════════════════════ */
const FraudPanel = ({ fraud_flags }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
    <Card>
      <Eyebrow>Fraud signal detection</Eyebrow>
      <h3 style={{ fontSize: 20, fontWeight: 800, color: T.ink, marginBottom: 20 }}>Authenticity check</h3>
      {fraud_flags?.length > 0 ? fraud_flags.map((f, i) => (
        <div key={i} style={{ padding: "16px 18px", marginBottom: 12, borderRadius: 14,
          background: f.severity === "High" ? T.softRed : T.softAmber,
          border: `1px solid ${f.severity === "High" ? "#FECACA" : "#FDE68A"}` }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}>
            <Badge color={f.severity === "High" ? T.red : T.amber}
              bg={f.severity === "High" ? "#FEE2E2" : "#FEF3C7"}>{f.severity}</Badge>
            <span style={{ fontSize: 14, fontWeight: 700, color: T.ink }}>{f.type?.replace(/_/g," ")}</span>
          </div>
          <div style={{ fontSize: 13, color: T.muted }}>{f.detail}</div>
        </div>
      )) : (
        <div style={{ display: "flex", gap: 18, alignItems: "center", padding: "24px 22px",
          borderRadius: 16, background: T.softGreen, border: `1px solid #BBF7D0` }}>
          <div style={{ fontSize: 38 }}>✅</div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: T.ink, marginBottom: 5 }}>No fraud flags detected</div>
            <div style={{ fontSize: 13, color: T.muted }}>All documents passed authenticity checks. Profile appears clean.</div>
          </div>
        </div>
      )}
    </Card>

    {/* What we check */}
    <Card>
      <Eyebrow>Detection methodology</Eyebrow>
      <h3 style={{ fontSize: 18, fontWeight: 800, color: T.ink, marginBottom: 16 }}>What PRISM checks for</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 12 }}>
        {[
          { icon: "🔍", title: "Metadata integrity", desc: "PDF creation timestamps, author fields, and edit history are verified against expected document properties." },
          { icon: "📐", title: "Transaction pattern analysis", desc: "Round-number salary credits, perfectly round EMIs, and suspiciously uniform cashflows are flagged." },
          { icon: "📅", title: "Date sequencing", desc: "Out-of-sequence transactions, future-dated entries, and missing weekend gaps trigger review." },
          { icon: "🔗", title: "Cross-document consistency", desc: "Salary amounts across payslips and bank credits are reconciled. Mismatches surface as flags." },
          { icon: "💹", title: "Balance trajectory", desc: "Sudden large credits just before assessment, or artificial balance inflation patterns, are detected." },
          { icon: "🏦", title: "IFSC and bank verification", desc: "All transaction IFSCs are validated against RBI's live IFSC database to catch fabricated entries." },
        ].map(({ icon, title, desc }) => (
          <div key={title} style={{ padding: "16px 14px", borderRadius: 14,
            background: T.bg, border: `1px solid ${T.border}` }}>
            <div style={{ fontSize: 22, marginBottom: 10 }}>{icon}</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: T.ink, marginBottom: 6 }}>{title}</div>
            <div style={{ fontSize: 12, color: T.muted, lineHeight: 1.65 }}>{desc}</div>
          </div>
        ))}
      </div>
    </Card>
  </div>
);

/* ═══════════════════════════════════════
   WHAT-IF
   Now wired to the real POST /assess/whatif backend endpoint instead
   of a fake timer. Requires the backend session to have already run
   /assess at least once (session.assessment_result must be set).
═══════════════════════════════════════ */
const WhatIfPanel = ({ session, baseResult }) => {
  const [overrides, setOverrides] = useState({});
  const [whatIf, setWhatIf] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const FIELDS = [
    { key: "cashflow_cv",        label: "Cashflow CV",          icon: "📊", step: "0.1",  min: 0, max: 3,   ph: "e.g. 0.4"   },
    { key: "credit_debit_ratio", label: "Credit / Debit ratio", icon: "💳", step: "0.1",  min: 0, max: 5,   ph: "e.g. 2.5"   },
    { key: "net_to_gross_ratio", label: "Net / Gross ratio",    icon: "💼", step: "0.01", min: 0, max: 1,   ph: "e.g. 0.85"  },
    { key: "min_balance",        label: "Min balance (₹)",      icon: "🏦", step: "500",  min: 0, max: 1e6, ph: "e.g. 25000" },
  ];

  const activeOverrides = Object.entries(overrides).filter(([, v]) => v !== undefined && !Number.isNaN(v));

  const simulate = async () => {
    if (activeOverrides.length === 0) {
      setErr("Enter at least one value to simulate.");
      return;
    }
    setErr(null);
    setLoading(true);
    try {
      const res = await fetch(`${BASE}/assess/whatif`, {
    method: "POST",
    headers: {
        "Content-Type": "application/json",
        "session-id": session.session_id,
    },
    body: JSON.stringify({
        overrides: Object.fromEntries(activeOverrides),
    }),
});
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail?.message || body?.detail || "Simulation failed");
      }
      const data = await res.json();
      setWhatIf(data);
    } catch (e) {
      setErr(e.message || "Something went wrong running the simulation.");
    } finally {
      setLoading(false);
    }
  };

  const baseScore = baseResult?.risk_score ?? null;
  const delta = whatIf && baseScore !== null ? whatIf.simulated_score - baseScore : null;
  const improved = delta !== null && delta > 0;
  const unchanged = delta !== null && delta === 0;

  // Build a plain-language narrative from the response
  const narrative = () => {
    if (!whatIf) return null;
    const changedLabels = activeOverrides
      .map(([k]) => FACTOR_META[k]?.label || k)
      .join(", ");
    if (unchanged) {
      return `Changing ${changedLabels} on their own wasn't enough to move your score — try a larger adjustment or combine it with another factor.`;
    }
    return `If you improve ${changedLabels}, your score would shift from ${baseScore} to ${whatIf.simulated_score} (${improved ? "+" : ""}${delta} pts), moving your risk tier ${
      whatIf.simulated_risk_tier !== baseResult?.risk_tier
        ? `from ${baseResult?.risk_tier} to ${whatIf.simulated_risk_tier}`
        : `— you'd remain in ${whatIf.simulated_risk_tier}`
    }.`;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <Card>
        <Eyebrow>Scenario simulation</Eyebrow>
        <h3 style={{ fontSize: 20, fontWeight: 800, color: T.ink, marginBottom: 6 }}>What-if analysis</h3>
        <p style={{ fontSize: 13, color: T.muted, marginBottom: 24, lineHeight: 1.7 }}>
          Adjust one or more values below to see exactly how your score would change.
          This re-runs the full scoring model with your overrides applied — not an estimate.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
          {FIELDS.map(({ key, label, icon, step, min, max, ph }) => (
            <div key={key}>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13,
                fontWeight: 600, color: T.ink, marginBottom: 8 }}>
                <span>{icon}</span> {label}
              </label>
              <input type="number" step={step} min={min} max={max} placeholder={ph}
                style={{ width: "100%", padding: "12px 16px", boxSizing: "border-box",
                  border: `1.5px solid ${T.border}`, borderRadius: 12, fontSize: 14,
                  color: T.ink, background: T.bg, outline: "none", fontFamily: "inherit" }}
                onChange={e => {
                  const v = e.target.value === "" ? undefined : parseFloat(e.target.value);
                  setOverrides(o => ({ ...o, [key]: v }));
                }} />
            </div>
          ))}
        </div>

        {err && (
          <div style={{ marginBottom: 16, padding: "12px 16px", borderRadius: 12,
            background: T.softRed, color: T.red, fontSize: 13, fontWeight: 600 }}>
            {err}
          </div>
        )}

        <button onClick={simulate} disabled={loading} style={{
          padding: "13px 32px",
          background: loading ? T.muted : `linear-gradient(135deg, ${T.coral}, ${T.purple})`,
          color: "#fff", border: "none", borderRadius: 12, fontSize: 14, fontWeight: 700,
          cursor: loading ? "default" : "pointer",
        }}>
          {loading ? "Running simulation…" : "Run simulation →"}
        </button>
      </Card>

      {whatIf && (
        <>
          {/* Headline result */}
          <Card style={{
            background: unchanged ? T.softAmber : improved ? T.softGreen : T.softRed,
            border: `1px solid ${unchanged ? "#FDE68A" : improved ? "#86EFAC" : "#FCA5A5"}`,
          }}>
            <div style={{ display: "flex", gap: 48, alignItems: "center", flexWrap: "wrap", marginBottom: 16 }}>
              {[
                { label: "Current score", val: baseScore, color: T.ink },
                { label: "→", val: null },
                { label: "Simulated score", val: whatIf.simulated_score,
                  color: unchanged ? T.amber : improved ? T.green : T.red },
                { label: "Change", val: `${delta >= 0 ? "+" : ""}${delta} pts`,
                  color: unchanged ? T.amber : improved ? T.green : T.red },
              ].map(({ label, val, color }, i) => (
                <div key={i}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: T.muted, textTransform: "uppercase",
                    letterSpacing: "0.1em", marginBottom: 4 }}>{label}</div>
                  {val !== null && <div style={{ fontSize: 38, fontWeight: 800, color: color ?? T.ink, lineHeight: 1 }}>{val}</div>}
                </div>
              ))}
            </div>
            <p style={{ fontSize: 14, color: T.ink, lineHeight: 1.7, fontWeight: 500 }}>
              {narrative()}
            </p>
          </Card>

          {/* Feature-level breakdown */}
          <Card>
            <Eyebrow>Factor breakdown</Eyebrow>
            <h3 style={{ fontSize: 17, fontWeight: 800, color: T.ink, marginBottom: 14 }}>What changed, and why it matters</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {Object.entries(whatIf.overrides_applied || {}).map(([key, val], i) => {
                const meta = FACTOR_META[key] || { icon: "📌", label: key, desc: "" };
                const woe = whatIf.feature_woe_values?.[key];
                return (
                  <div key={i} style={{ display: "flex", gap: 14, alignItems: "flex-start",
                    padding: "14px 16px", borderRadius: 14, background: T.bg, border: `1px solid ${T.border}` }}>
                    <div style={{ width: 36, height: 36, borderRadius: 10, fontSize: 16, flexShrink: 0,
                      display: "flex", alignItems: "center", justifyContent: "center", background: T.softPurple }}>
                      {meta.icon}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: T.ink }}>{meta.label}</div>
                      <div style={{ fontSize: 12, color: T.muted, marginTop: 2 }}>
                        You entered <strong style={{ color: T.ink }}>{val}</strong>
                        {woe !== undefined && <> → new WoE value of <strong style={{ color: T.ink }}>{woe}</strong></>}
                      </div>
                    </div>
                  </div>
                );
              })}
              {whatIf.ignored_keys?.length > 0 && (
                <div style={{ fontSize: 12, color: T.muted, fontStyle: "italic", marginTop: 4 }}>
                  Note: {whatIf.ignored_keys.join(", ")} {whatIf.ignored_keys.length > 1 ? "aren't" : "isn't"} used by the scoring model and {whatIf.ignored_keys.length > 1 ? "were" : "was"} ignored.
                </div>
              )}
            </div>
          </Card>

          {/* Takeaway bullets */}
          <Card style={{ background: T.softBlue, border: "1px solid #BFDBFE" }}>
            <div style={{ display: "flex", gap: 18, alignItems: "flex-start" }}>
              <div style={{ fontSize: 30, flexShrink: 0 }}>💡</div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: T.ink, marginBottom: 10 }}>Key takeaways</div>
                <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 6 }}>
                  <li style={{ fontSize: 13, color: "#1E40AF", lineHeight: 1.7 }}>
                    Your simulated risk tier is <strong>{whatIf.simulated_risk_tier}</strong>, compared to <strong>{baseResult?.risk_tier}</strong> today.
                  </li>
                  <li style={{ fontSize: 13, color: "#1E40AF", lineHeight: 1.7 }}>
                    Simulated probability of default: <strong>{(whatIf.simulated_pd * 100).toFixed(1)}%</strong>.
                  </li>
                  <li style={{ fontSize: 13, color: "#1E40AF", lineHeight: 1.7 }}>
                    This is a projection based on the values you entered — it doesn't submit new documents or change your actual score.
                  </li>
                </ul>
              </div>
            </div>
          </Card>
        </>
      )}
    </div>
  );
};

/* ═══════════════════════════════════════
   MAIN PAGE
═══════════════════════════════════════ */
export default function ResultsPage({ go, session, result, setError }) {
  const [tab, setTab] = useState("score");

  // Use mock data when rendered standalone
  const data    = result  ?? MOCK_RESULT;
  const sess    = session ?? MOCK_SESSION;
  const tier    = TIER_CONFIG[data?.risk_tier] ?? TIER_CONFIG["Medium Risk"];
  const score   = data?.risk_score ?? 0;

  if (!data) return null;

  return (
    <div style={{ minHeight: "100vh", ...DOT_BG, fontFamily: "'Inter', sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        input::-webkit-inner-spin-button, input::-webkit-outer-spin-button { -webkit-appearance: none; }
        input:focus { border-color: ${T.purple} !important; box-shadow: 0 0 0 3px ${T.purple}22; }
      `}</style>

      {/* Decorative blobs */}
      <div style={{ position: "fixed", top: -100, right: -100, width: 450, height: 450,
        borderRadius: "50%", pointerEvents: "none", zIndex: 0,
        background: `radial-gradient(circle at 40% 40%, ${tier.color}1A, transparent 70%)` }} />
      <div style={{ position: "fixed", bottom: -80, left: -80, width: 350, height: 350,
        borderRadius: "50%", pointerEvents: "none", zIndex: 0,
        background: `radial-gradient(circle at 60% 60%, ${T.purple}14, transparent 70%)` }} />

      {/* Nav bar */}
      <div style={{ background: "rgba(246,246,248,0.85)", backdropFilter: "blur(10px)",
        borderBottom: `1px solid ${T.border}`, position: "sticky", top: 0, zIndex: 100 }}>
        <div style={{ maxWidth: 1120, margin: "0 auto", padding: "0 40px",
          display: "flex", alignItems: "center", justifyContent: "space-between", height: 60 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 30, height: 30, borderRadius: 8,
              background: `linear-gradient(135deg, ${T.coral}, ${T.purple})`,
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "#fff", fontSize: 13, fontWeight: 800 }}>P</div>
            <span style={{ fontSize: 16, fontWeight: 800, color: T.ink }}>PRISM</span>
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            <button onClick={() => go?.("login")} style={{
              padding: "8px 20px", borderRadius: 10, border: `1.5px solid ${T.border}`,
              background: T.white, fontSize: 13, fontWeight: 600, cursor: "pointer", color: T.ink,
            }}>← New assessment</button>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "44px 40px 100px", position: "relative", zIndex: 1 }}>

        {/* Page header */}
        <div style={{ marginBottom: 28 }}>
          <Eyebrow>Assessment complete</Eyebrow>
          <h1 style={{ fontSize: 28, fontWeight: 800, color: T.ink, marginTop: 6, letterSpacing: "-0.4px" }}>
            Credit Risk Report
          </h1>
          <div style={{ fontSize: 12, color: T.muted, marginTop: 5 }}>
            {sess?.borrowerId && <><strong style={{ color: T.ink }}>{sess.borrowerId}</strong> · </>}
            {data.assessed_at ? new Date(data.assessed_at).toLocaleString("en-IN") : ""}
          </div>
        </div>

        <ScoreHero result={data} tier={tier} score={score} />
        <TabBar active={tab} onChange={setTab} />

        {tab === "score"    && <ScorePanel    result={data} />}
        {tab === "features" && <FeaturesPanel features={data.features} />}
        {tab === "improve"  && <ImprovePanel  result={data} />}
        {tab === "learn"    && <Credit101Panel />}
        {tab === "fraud"    && <FraudPanel    fraud_flags={data.fraud_flags} />}
        {tab === "whatif"   && <WhatIfPanel   session={sess} baseResult={data} />}

        {/* Warnings */}
        {data.warnings?.length > 0 && (
          <div style={{ marginTop: 28, padding: "16px 22px", borderRadius: 16,
            background: T.softAmber, border: `1px solid #FDE68A` }}>
            <Eyebrow color={T.amber}>Data quality notes</Eyebrow>
            {data.warnings.map((w, i) => (
              <div key={i} style={{ fontSize: 13, color: "#92400E", padding: "3px 0" }}>· {w}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}