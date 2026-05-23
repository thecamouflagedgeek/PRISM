// src/pages/ConsentPage.jsx
import { Nav } from "../components/Nav";

const BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const CONSENT_ITEMS = [
  { key: "bank",    label: "Bank Statement Access",       required: true,
    desc: "We will extract transaction data, cashflow signals, and income patterns from your bank statement.",
    icon: "🏦" },
  { key: "salary",  label: "Salary Slip Access",          required: false,
    desc: "Optional. Improves scoring accuracy by adding employment income verification.",
    icon: "💼" },
  { key: "utility", label: "Utility Bill Access",         required: false,
    desc: "Optional. Payment discipline score from electricity, water, and telecom bills.",
    icon: "⚡" },
  { key: "bureau",  label: "Credit Bureau Pull",          required: false,
    desc: "Optional. Adds CIBIL/bureau data to your assessment if available.",
    icon: "📊" },
  { key: "dpdpa",   label: "DPDPA 2023 Acknowledgement",  required: true,
    desc: "You acknowledge that your data will be processed under India's Digital Personal Data Protection Act, 2023.",
    icon: "📋" },
];

export default function ConsentPage({ go, session, setSession, consents, setConsents, setError }) {

  const handleConsent = async () => {
    try {
      const res = await fetch(`${BASE}/consent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          borrower_id:     session.borrowerId,
          consent_bank:    consents.bank,
          consent_salary:  consents.salary,
          consent_utility: consents.utility,
          consent_bureau:  consents.bureau,
          consent_dpdpa:   consents.dpdpa,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail?.message || "Consent failed");
      setSession(s => ({ ...s, id: data.session_id }));
      go("upload");
    } catch (e) {
      setError(e.message);
    }
  };

  const toggle = (key) => {
    const item = CONSENT_ITEMS.find(c => c.key === key);
    if (item?.required) return;
    setConsents(c => ({ ...c, [key]: !c[key] }));
  };

  const canProceed = consents.bank && consents.dpdpa;

  return (
    <div className="dot-grid" style={{ minHeight: "100vh" }}>
      <Nav currentPage="consent" onLogoClick={() => go("landing")} />

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "64px 48px",
        display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: 80, alignItems: "start" }}>

        {/* Left — intro */}
        <div style={{ position: "sticky", top: 96 }}>
          <div className="fade-up" style={{ fontSize: 12, fontWeight: 600, color: "var(--orange)",
            textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 12,
            fontFamily: "'Syne', sans-serif" }}>Step 2 of 4</div>
          <h1 className="display fade-up-1" style={{ fontSize: 44, color: "var(--ink)", marginBottom: 16 }}>
            Your Data,<br />
            <span style={{ color: "var(--orange)" }}>Your Choice.</span>
          </h1>
          <p className="fade-up-2" style={{ color: "var(--muted)", fontSize: 15, lineHeight: 1.7,
            fontWeight: 300, marginBottom: 32 }}>
            Hi <strong style={{ color: "var(--ink)" }}>{session?.borrowerId}</strong>.
            Select which data sources you consent to share.
            Mandatory items are required to proceed. Optional items improve your score accuracy.
          </p>

          {/* Data usage card */}
          <div className="fade-up-3 card" style={{ padding: "20px 22px" }}>
            <div className="heading" style={{ fontSize: 14, marginBottom: 12 }}>How we use your data</div>
            {[
              "Data is processed only for this assessment session",
              "PII is masked in all outputs and logs",
              "Session expires in 60 minutes automatically",
              "You can withdraw consent at any time",
            ].map((l, i) => (
              <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start",
                marginBottom: 8, fontSize: 13, color: "var(--muted)" }}>
                <span style={{ color: "var(--green)", marginTop: 1 }}>✓</span>
                {l}
              </div>
            ))}
          </div>

          {/* Blob decoration */}
          <div className="blob blob-orange float-anim"
            style={{ width: 100, height: 100, opacity: 0.25, marginTop: 32,
              borderRadius: "60% 40% 55% 45% / 50% 60% 40% 60%" }} />
        </div>

        {/* Right — consent list */}
        <div className="fade-up-2" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {CONSENT_ITEMS.map(({ key, label, desc, icon, required }) => {
            const active = consents[key];
            return (
              <div key={key}
                className={`consent-row ${active ? "active" : ""} ${required ? "required-row" : ""}`}
                onClick={() => toggle(key)}>
                <div style={{ fontSize: 22, marginTop: 2 }}>{icon}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)" }}>{label}</span>
                    {required && (
                      <span style={{ fontSize: 10, fontWeight: 600, padding: "2px 7px",
                        borderRadius: 50, background: "#FEE2E2", color: "#DC2626" }}>Required</span>
                    )}
                    {!required && (
                      <span style={{ fontSize: 10, fontWeight: 500, padding: "2px 7px",
                        borderRadius: 50, background: "var(--cream)", color: "var(--muted)",
                        border: "1px solid var(--border)" }}>Optional</span>
                    )}
                  </div>
                  <div style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.55 }}>{desc}</div>
                </div>
                <div className={`consent-check ${active ? "checked" : ""}`}>
                  {active && <span style={{ color: "#fff", fontSize: 12, fontWeight: 700 }}>✓</span>}
                </div>
              </div>
            );
          })}

          <div style={{ marginTop: 8, padding: "16px 18px", borderRadius: 12,
            background: "var(--cream)", border: "1px solid var(--border)" }}>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>
              <strong style={{ color: "var(--ink)" }}>Consents selected: </strong>
              {Object.entries(consents).filter(([, v]) => v).map(([k]) => k).join(", ") || "None"}
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
            <button className="btn-outline" onClick={() => go("login")} style={{ flex: "0 0 auto" }}>
              ← Back
            </button>
            <button className="btn-primary btn-orange"
              onClick={handleConsent} disabled={!canProceed}
              style={{ flex: 1, justifyContent: "center", padding: "14px" }}>
              Record Consent & Continue →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}