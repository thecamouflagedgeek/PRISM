// src/pages/LandingPage.jsx
import { Nav } from "../components/Nav";
import { PageShell } from "../components/PageShell";
import { useLanguage } from "../components/LanguageContext";
import { translations } from "../translations";

export default function LandingPage({ go }) {
  const { language } = useLanguage();
  const t = translations[language];
  
  return (
<PageShell glowColor="rgba(232,104,58,0.80)">
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

          <h1>{t.heroTitle}</h1>

<p>{t.heroDesc}</p>

<button>{t.getStarted}</button>

          <h1
  className="display fade-up-1"
  style={{
    fontSize: "clamp(44px,5vw,64px)",
    color: "var(--ink)",
    marginBottom: 16,
  }}
>
  {t.heroTitle}
</h1>

          <p
  className="fade-up-2"
  style={{
    fontSize: 17,
    color: "var(--muted)",
    lineHeight: 1.65,
    maxWidth: 420,
    marginBottom: 36,
    fontWeight: 300,
  }}
>
  {t.heroDesc}
</p>

          <div className="fade-up-3" style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <button className="btn-primary btn-orange" onClick={() => go("login")}
              style={{ padding: "13px 28px", fontSize: 15 }}>
              {t.getStarted} →
            </button>
            <button className="btn-outline" style={{ padding: "12px 22px" }}>
              {t.viewDemo}
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

        {/* Right — 3D PRISM sculpture */}
        <div className="fade-up-2 dot-overlay" style={{
          display: "flex", justifyContent: "center", alignItems: "center",
          position: "relative", height: 540, overflow: "hidden",
        }}>

          {/* Ambient particles */}
          <div className="particle p1" />
          <div className="particle p2" />
          <div className="particle p3" />
          <div className="particle p4" />

          {/* CSS 3D prism */}
          <div className="prism-scene">
            <div className="prism-glow" />
            <div className="prism">
              <div className="prism-face prism-front" />
              <div className="prism-face prism-left" />
              <div className="prism-face prism-right" />
              <div className="prism-shine" />
            </div>
          </div>

          {/* Spectral light rays below prism */}
          <div className="spectral-rays">
            <div className="ray ray-1" />
            <div className="ray ray-2" />
            <div className="ray ray-3" />
            <div className="ray ray-4" />
            <div className="ray ray-5" />
            <div className="ray ray-6" />
          </div>

          {/* Score card — bottom left 
          <div style={{
            position: "absolute", bottom: 52, left: 8, zIndex: 10,
            background: "rgba(255,255,255,0.84)",
            backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)",
            borderRadius: 20, padding: "18px 22px",
            boxShadow: "0 20px 52px rgba(0,0,0,0.10), inset 0 1px 0 rgba(255,255,255,0.8)",
            border: "1px solid rgba(255,255,255,0.75)",
            minWidth: 190, animation: "fadeUp 0.6s 0.8s ease both",
          }}>
            <div style={{ fontSize: 10, color: "var(--muted)", fontWeight: 600,
              textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>Risk Score</div>
            <div className="heading" style={{ fontSize: 44, color: "var(--orange)", lineHeight: 1 }}>742</div>
            <div style={{ fontSize: 12, color: "var(--green)", fontWeight: 600,
              marginTop: 6, display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ fontSize: 8 }}>●</span> Medium Risk
            </div>
            <div style={{ marginTop: 10, height: 3, borderRadius: 2, background: "var(--border)" }}>
              <div style={{ height: "100%", width: "60%", borderRadius: 2,
                background: "linear-gradient(90deg, var(--orange), #F59E0B)" }} />
            </div>
          </div>*/}

          {/* SHAP chip — top right 
          <div style={{
            position: "absolute", top: 86, right: 8, zIndex: 10,
            background: "rgba(17,17,16,0.90)",
            backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)",
            borderRadius: 12, padding: "10px 15px",
            color: "#fff", fontSize: 12, fontWeight: 500,
            boxShadow: "0 10px 32px rgba(0,0,0,0.22)",
            border: "1px solid rgba(255,255,255,0.1)",
            animation: "fadeUp 0.6s 1.0s ease both",
            display: "flex", alignItems: "center", gap: 7,
          }}>
            <span style={{ color: "var(--green)", fontWeight: 700 }}>+</span>
            Salary regular · +38 pts
          </div>*/}

          {/* Fraud clear chip
          <div style={{
            position: "absolute", top: 164, right: 8, zIndex: 10,
            background: "rgba(34,197,94,0.10)",
            backdropFilter: "blur(10px)", WebkitBackdropFilter: "blur(10px)",
            borderRadius: 10, padding: "8px 13px",
            border: "1px solid rgba(34,197,94,0.28)",
            animation: "fadeUp 0.6s 1.2s ease both",
            display: "flex", alignItems: "center", gap: 6,
          }}>
            <span style={{ fontSize: 11, color: "var(--green)" }}>✓</span>
            <span style={{ fontSize: 11, color: "var(--green)", fontWeight: 600 }}>No fraud flags</span>
          </div>*/}

          {/* Top factor chip — bottom right
          <div style={{
            position: "absolute", bottom: 100, right: 8, zIndex: 10,
            background: "rgba(124,92,246,0.10)",
            backdropFilter: "blur(10px)", WebkitBackdropFilter: "blur(10px)",
            borderRadius: 10, padding: "9px 13px",
            border: "1px solid rgba(124,92,246,0.28)",
            animation: "fadeUp 0.6s 1.4s ease both",
          }}>
            <div style={{ fontSize: 10, color: "var(--purple)", fontWeight: 600,
              textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 3 }}>Top factor</div>
            <div style={{ fontSize: 11, color: "var(--purple)", fontWeight: 500 }}>EMI discipline · +42 pts</div>
          </div>*/}

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
                <div key={n} style={{ padding: "20px 18px", borderRadius: "var(--r-md)",
                  border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.03)" }}>
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
    </PageShell>
  );
}