// src/pages/LandingPage.jsx
import { Nav } from "../components/Nav";
import { PageShell } from "../components/PageShell";
import { useLanguage } from "../components/LanguageContext";
import { useTranslation } from "react-i18next";

export default function LandingPage({ go }) {
  const { language } = useLanguage();
  const { t } = useTranslation();
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
              {t('landing.badge')}
            </span>
          </div>

          <h1>{t('landing.heroTitle')}</h1>

<p>{t('landing.heroDesc')}</p>

<button>{t('landing.getStarted')}</button>

          <h1
  className="display fade-up-1"
  style={{
    fontSize: "clamp(44px,5vw,64px)",
    color: "var(--ink)",
    marginBottom: 16,
  }}
>
  {t('landing.heroTitle')}
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
  {t('landing.heroDesc')}
</p>

          <div className="fade-up-3" style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <button className="btn-primary btn-orange" onClick={() => go("login")}
              style={{ padding: "13px 28px", fontSize: 15 }}>
              {t('landing.getStarted')} →
            </button>
            <button className="btn-outline" style={{ padding: "12px 22px" }}>
              {t('landing.viewDemo')}
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

        </div>
      </section>

      {/* ── Trusted by ── */}
      <section style={{ borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)",
        padding: "20px 48px", display: "flex", alignItems: "center", gap: 48,
        background: "var(--white)", overflow: "hidden" }}>
        <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 500, whiteSpace: "nowrap" }}>
          {t('landing.trustedBy')}
        </span>
        {[
          t('landing.trustedItems.nbfcs'),
          t('landing.trustedItems.microfinance'),
          t('landing.trustedItems.banks'),
          t('landing.trustedItems.thinFile'),
          t('landing.trustedItems.msmes'),
          t('landing.trustedItems.ruralIndia')
        ].map(l => (
          <span key={l} style={{ fontSize: 14, color: "var(--ink2)", fontWeight: 500,
            opacity: 0.6, whiteSpace: "nowrap" }}>{l}</span>
        ))}
      </section>

      {/* ── Three pillars ── */}
      <section style={{ maxWidth: 1100, margin: "80px auto", padding: "0 48px" }}>
        <div style={{ textAlign: "center", marginBottom: 56 }}>
          <h2 className="heading" style={{ fontSize: 38, color: "var(--ink)", marginBottom: 12 }}>
            {t('landing.threePillars.title')}
          </h2>
          <p style={{ color: "var(--muted)", fontSize: 16, fontWeight: 300 }}>
            {t('landing.threePillars.subtitle')}
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20 }}>
          {[
            {
              blob: "blob-orange",
              title: t('landing.threePillars.bank.title'),
              sub: t('landing.threePillars.bank.desc'),
              tag: t('landing.threePillars.bank.tag'),
            },
            {
              blob: "blob-purple",
              title: t('landing.threePillars.salary.title'),
              sub: t('landing.threePillars.salary.desc'),
              tag: t('landing.threePillars.salary.tag'),
            },
            {
              blob: "blob-blue",
              title: t('landing.threePillars.utility.title'),
              sub: t('landing.threePillars.utility.desc'),
              tag: t('landing.threePillars.utility.tag'),
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
                  {t('landing.threePillars.learnMore')}
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
                {t('landing.howItWorks.title')}
              </h2>
              <p style={{ color: "rgba(255,255,255,0.45)", fontSize: 15, lineHeight: 1.65,
                fontWeight: 300 }}>
                {t('landing.howItWorks.desc')}
              </p>
              <button className="btn-primary btn-orange" onClick={() => go("login")}
                style={{ marginTop: 28 }}>
                {t('landing.assessmentBtn')}
              </button>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, flex: 1, minWidth: 320 }}>
              {[
                { n: t('landing.howItWorks.step1.num'), t: t('landing.howItWorks.step1.title'), d: t('landing.howItWorks.step1.desc') },
                { n: t('landing.howItWorks.step2.num'), t: t('landing.howItWorks.step2.title'), d: t('landing.howItWorks.step2.desc') },
                { n: t('landing.howItWorks.step3.num'), t: t('landing.howItWorks.step3.title'), d: t('landing.howItWorks.step3.desc') },
                { n: t('landing.howItWorks.step4.num'), t: t('landing.howItWorks.step4.title'), d: t('landing.howItWorks.step4.desc') },
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
          {t('landing.cta.title')}
        </h2>
        <p style={{ color: "var(--muted)", marginBottom: 28, fontSize: 15 }}>
          {t('landing.cta.desc')}
        </p>
        <button className="btn-primary btn-orange" onClick={() => go("login")}
          style={{ padding: "14px 32px", fontSize: 15 }}>
          {t('landing.readyBtn')}
        </button>
      </section>

      {/* ── Footer ── */}
      <footer style={{ borderTop: "1px solid var(--border)", padding: "28px 48px",
        display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 12, color: "var(--muted)" }}>
          {t('landing.footer.copy')}
        </div>
        <div style={{ display: "flex", gap: 20 }}>
          {[t('landing.footer.privacy'), t('landing.footer.terms')].map(l => (
            <span key={l} style={{ fontSize: 12, color: "var(--muted)", cursor: "pointer" }}>{l}</span>
          ))}
        </div>
      </footer>
    </PageShell>
  );
}