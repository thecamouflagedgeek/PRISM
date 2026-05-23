// src/pages/LoginPage.jsx
import { useState } from "react";
import { Nav } from "../components/Nav";

export default function LoginPage({ go, setSession }) {
  const [bid, setBid] = useState("");

  const handleContinue = () => {
    if (!bid.trim()) return;
    setSession({ borrowerId: bid.trim(), id: null });
    go("consent");
  };

  return (
    <div className="dot-grid" style={{ minHeight: "100vh" }}>
      <Nav currentPage="login" onLogoClick={() => go("landing")} />

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "72px 48px",
        display: "grid", gridTemplateColumns: "1fr 1fr", gap: 80, alignItems: "center" }}>

        {/* Left — form */}
        <div>
          <div className="fade-up" style={{ fontSize: 12, fontWeight: 600, color: "var(--orange)",
            textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 12,
            fontFamily: "'Syne', sans-serif" }}>
            Step 1 of 4
          </div>
          <h1 className="display fade-up-1" style={{ fontSize: 48, color: "var(--ink)", marginBottom: 12 }}>
            Welcome to<br />
            <span style={{ color: "var(--orange)" }}>PRISM.</span>
          </h1>
          <p className="fade-up-2" style={{ color: "var(--muted)", fontSize: 16, lineHeight: 1.65,
            fontWeight: 300, marginBottom: 40 }}>
            Enter your Borrower ID to begin your credit assessment.
            Your session is encrypted and expires in 60 minutes.
          </p>

          <div className="fade-up-3" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={{ fontSize: 13, fontWeight: 500, color: "var(--ink2)",
                display: "block", marginBottom: 8 }}>Borrower ID</label>
              <input
                className="input-field"
                value={bid}
                onChange={e => setBid(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleContinue()}
                placeholder="e.g. BRW-2025-001"
                style={{ fontFamily: "'Syne', sans-serif", letterSpacing: "0.02em" }}
              />
              <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 6 }}>
                Use any identifier — no account creation required.
              </div>
            </div>

            <button className="btn-primary btn-orange"
              onClick={handleContinue} disabled={!bid.trim()}
              style={{ padding: "14px 28px", fontSize: 15, alignSelf: "flex-start" }}>
              Continue to Consent →
            </button>
          </div>

          {/* Trust signals */}
          <div className="fade-up-4" style={{ display: "flex", gap: 20, marginTop: 40,
            paddingTop: 28, borderTop: "1px solid var(--border)" }}>
            {[
              { icon: "🔒", label: "AES-256 encrypted" },
              { icon: "📋", label: "DPDPA 2023 aligned" },
              { icon: "⏱", label: "60-min session" },
            ].map(({ icon, label }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 14 }}>{icon}</span>
                <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 500 }}>{label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right — visual */}
        <div className="fade-up-2" style={{ position: "relative", height: 420,
          display: "flex", justifyContent: "center", alignItems: "center" }}>

          <div className="blob blob-orange float-anim"
            style={{ width: 240, height: 280, opacity: 0.6,
              borderRadius: "55% 45% 65% 35% / 55% 65% 35% 45%" }} />

          <div className="blob blob-blue"
            style={{ width: 130, height: 130, position: "absolute", bottom: 40, right: 20,
              opacity: 0.5, animation: "float 6s 0.8s ease-in-out infinite" }} />

          {/* Session card */}
          <div style={{ position: "absolute", background: "var(--white)", borderRadius: 14,
            padding: "16px 20px", boxShadow: "0 16px 40px rgba(0,0,0,0.08)",
            border: "1px solid var(--border)", top: 40, right: 10, minWidth: 160 }}>
            <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase",
              letterSpacing: "0.1em", marginBottom: 6 }}>Session</div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--green)" }} />
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>Secure</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
              TLS 1.3 · AES-256
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}