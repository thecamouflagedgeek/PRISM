// src/pages/LandingPage.jsx
import { Nav } from "../components/Nav";

export default function LandingPage({ go }) {
  return (
    <div className="dot-grid" style={{ minHeight: "100vh", background: "var(--cream)" }}>
      <Nav currentPage="landing" onLogoClick={() => {}} />

      {/* ── Hero ── */}
      <section style={{ maxWidth: 1100, margin: "0 auto", padding: "72px 48px 80px",
        display: "grid", gridTemplateColumns: "1fr 1fr", gap: 48, alignItems: "center" }}>

        {/* Left */}
        <div>
          <div className="fade-up" style={{ display: "inline-flex", alignItems: "center", gap: 8,
            padding: "5px 14px", borderRadius: 50, border: "1px solid var(--border)",
            background: "var(--white)", marginBottom: 28 }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--orange)" }} />
            <span style={{ fontSize: 12, fontWeight: 500, color: "var(--ink2)" }}>
              TIH IoT CHANAKYA Fellowship 2025
            </span>
          </div>

          <h1 className="display fade-up-1" style={{ fontSize: "clamp(44px, 5vw, 64px)", color: "var(--ink)", marginBottom: 16 }}>
            It's The{" "}
            <span style={{ color: "var(--orange)" }}>Smarter</span>{" "}
            Way To Assess Credit.
          </h1>

          <p className="fade-up-2" style={{ fontSize: 17, color: "var(--muted)", lineHeight: 1.65,
            maxWidth: 420, marginBottom: 36, fontWeight: 300 }}>
            PRISM replaces bureau-only scoring with multi-modal AI — bank behaviour,
            employment continuity, and payment discipline in one explainable score.
          </p>

          <div className="fade-up-3" style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <button className="btn-primary btn-orange" onClick={() => go("login")}
              style={{ padding: "13px 28px", fontSize: 15 }}>
              Get Started →
            </button>
            <button className="btn-outline" style={{ padding: "12px 22px" }}>
              View Demo
            </button>
          </div>

          {/* Stat row */}
          <div className="fade-up-4" style={{ display: "flex", gap: 32, marginTop: 48,
            paddingTop: 32, borderTop: "1px solid var(--border)" }}>
            {[
              { n: "190M+", l: "Credit-invisible citizens in India" },
              { n: "TRL-4",  l: "Lab prototype stage" },
              { n: "8",      l: "Pipeline stages" },
            ].map(({ n, l }) => (
              <div key={n}>
                <div className="heading" style={{ fontSize: 26, color: "var(--ink)" }}>{n}</div>
                <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2, maxWidth: 100 }}>{l}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Right — blob sculpture */}
        <div className="fade-up-2" style={{ display: "flex", justifyContent: "center", alignItems: "center",
          position: "relative", height: 480 }}>

          {/* Main blob */}
          <div className="blob blob-orange float-anim" style={{ width: 280, height: 320,
            position: "absolute", top: 60, left: "50%", transform: "translateX(-50%)",
            opacity: 0.85 }} />

          {/* Secondary blob */}
          <div className="blob blob-purple" style={{ width: 140, height: 160,
            position: "absolute", bottom: 80, right: 40,
            borderRadius: "40% 60% 50% 70% / 60% 40% 70% 50%",
            opacity: 0.6, animation: "float 7s 1s ease-in-out infinite" }} />

          {/* Score preview card */}
          <div style={{ position: "absolute", bottom: 60, left: 20, zIndex: 10,
            background: "var(--white)", borderRadius: 16, padding: "16px 20px",
            boxShadow: "0 16px 48px rgba(0,0,0,0.1)", border: "1px solid var(--border)",
            minWidth: 180 }}>
            <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500, textTransform: "uppercase",
              letterSpacing: "0.08em", marginBottom: 4 }}>Risk Score</div>
            <div className="heading" style={{ fontSize: 36, color: "var(--orange)" }}>742</div>
            <div style={{ fontSize: 12, color: "var(--green)", fontWeight: 500, marginTop: 2,
              display: "flex", alignItems: "center", gap: 4 }}>
              <span>●</span> Medium Risk
            </div>
          </div>

          {/* SHAP tag */}
          <div style={{ position: "absolute", top: 80, right: 20, zIndex: 10,
            background: "var(--ink)", borderRadius: 12, padding: "10px 14px",
            color: "#fff", fontSize: 11, fontWeight: 500, boxShadow: "0 8px 24px rgba(0,0,0,0.2)" }}>
            + Salary regular · +38 pts
          </div>
        </div>
      </section>

      {/* ── Trusted by ── */}
      <section style={{ borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)",
        padding: "20px 48px", display: "flex", alignItems: "center", gap: 48,
        background: "var(--white)", overflow: "hidden" }}>
        <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 500, whiteSpace: "nowrap" }}>
          Designed for
        </span>
        {["NBFCs", "Microfinance", "Banks", "Thin-file borrowers", "MSMEs", "Rural India"].map(l => (
          <span key={l} style={{ fontSize: 14, color: "var(--ink2)", fontWeight: 500,
            opacity: 0.6, whiteSpace: "nowrap" }}>{l}</span>
        ))}
      </section>

      {/* ── Three pillars ── */}
      <section style={{ maxWidth: 1100, margin: "80px auto", padding: "0 48px" }}>
        <div style={{ textAlign: "center", marginBottom: 56 }}>
          <h2 className="heading" style={{ fontSize: 38, color: "var(--ink)", marginBottom: 12 }}>
            Let Your Data Do The Scoring.
          </h2>
          <p style={{ color: "var(--muted)", fontSize: 16, fontWeight: 300 }}>
            Three document sources. One explainable risk score. Full audit trail.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20 }}>
          {[
            {
              blob: "blob-orange",
              title: "Bank Statement",
              sub: "Cashflow, income regularity, EMI detection, spending patterns",
              tag: "BA-01 · BA-02",
            },
            {
              blob: "blob-purple",
              title: "Salary Slip",
              sub: "Net-to-gross ratio, PF contribution, employer stability",
              tag: "BA-03",
            },
            {
              blob: "blob-blue",
              title: "Utility Bills",
              sub: "Payment discipline, on-time rate, billing consistency",
              tag: "CS-01",
            },
          ].map(({ blob, title, sub, tag }) => (
            <div key={title} className="card" style={{ position: "relative", overflow: "hidden" }}>
              <div className={`blob ${blob}`}
                style={{ width: 120, height: 120, position: "absolute", top: -30, right: -30,
                  opacity: 0.35, borderRadius: "50% 40% 60% 50% / 60% 50% 50% 40%" }} />
              <div style={{ position: "relative", zIndex: 1 }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: "var(--muted)",
                  textTransform: "uppercase", letterSpacing: "0.08em",
                  marginBottom: 16, fontFamily: "'Syne', sans-serif" }}>{tag}</div>
                <div className="heading" style={{ fontSize: 22, marginBottom: 10 }}>{title}</div>
                <p style={{ fontSize: 14, color: "var(--muted)", lineHeight: 1.6 }}>{sub}</p>
                <div style={{ marginTop: 20, fontSize: 13, fontWeight: 500, color: "var(--orange)",
                  display: "flex", alignItems: "center", gap: 4 }}>
                  Learn more →
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── How it works ── */}
      <section style={{ background: "var(--ink)", padding: "80px 48px" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start",
            gap: 48, flexWrap: "wrap" }}>
            <div style={{ maxWidth: 380 }}>
              <h2 className="heading" style={{ fontSize: 38, color: "var(--white)", marginBottom: 16 }}>
                I Feel Like FinTech Tonight.
              </h2>
              <p style={{ color: "rgba(255,255,255,0.45)", fontSize: 15, lineHeight: 1.65,
                fontWeight: 300 }}>
                Explainable AI scoring. SHAP reason codes. What-if simulation.
                DPDPA 2023 aligned. All in one pipeline.
              </p>
              <button className="btn-primary btn-orange" onClick={() => go("login")}
                style={{ marginTop: 28 }}>
                Start Assessment →
              </button>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, flex: 1, minWidth: 320 }}>
              {[
                { n: "01", t: "Upload Documents",    d: "Bank statement, salary slip, utility bills" },
                { n: "02", t: "Parse & Validate",    d: "pdfplumber extraction + field confidence scoring" },
                { n: "03", t: "Feature Engineering", d: "Cashflow CV, payment discipline, employment signals" },
                { n: "04", t: "Explainable Score",   d: "300–900 score with SHAP reason codes + fraud flags" },
              ].map(({ n, t, d }) => (
                <div
  key={n}
  style={{
    padding: "20px 18px",
    borderRadius: "var(--r-md)",
    border: "1px solid rgba(255,255,255,0.08)",
    background: "rgba(255,255,255,0.03)"
  }}
>
                  <div style={{ fontSize: 11, color: "var(--orange)", fontWeight: 700,
                    fontFamily: "'Syne', sans-serif", marginBottom: 8 }}>{n}</div>
                  <div style={{ fontSize: 14, color: "var(--white)", fontWeight: 600,
                    marginBottom: 6 }}>{t}</div>
                  <div style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", lineHeight: 1.55 }}>{d}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section style={{ padding: "80px 48px", textAlign: "center" }}>
        <h2 className="heading" style={{ fontSize: 38, color: "var(--ink)", marginBottom: 12 }}>
          Ready to get started?
        </h2>
        <p style={{ color: "var(--muted)", marginBottom: 28, fontSize: 15 }}>
          Run a full credit assessment in under 60 seconds.
        </p>
        <button className="btn-primary btn-orange" onClick={() => go("login")}
          style={{ padding: "14px 32px", fontSize: 15 }}>
          Begin Assessment →
        </button>
      </section>

      {/* ── Footer ── */}
      <footer style={{ borderTop: "1px solid var(--border)", padding: "28px 48px",
        display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 12, color: "var(--muted)" }}>
          PRISM · TIH IoT CHANAKYA Fellowship 2025 · Fr. Conceicao Rodrigues College of Engineering
        </div>
        <div style={{ display: "flex", gap: 20 }}>
          {["Privacy Policy", "Terms"].map(l => (
            <span key={l} style={{ fontSize: 12, color: "var(--muted)", cursor: "pointer" }}>{l}</span>
          ))}
        </div>
      </footer>
    </div>
  );
}