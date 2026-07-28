// src/pages/LoginPage.jsx
import { useState } from "react";
import { Nav } from "../components/Nav";


const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
  

export default function LoginPage({ go, setSession,setError}){
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const handleContinue = async () => {
  const phoneNumber = phone.trim();

  if (!phoneNumber || loading) return;

  setLoading(true);

  try {
    const res = await fetch(`${API}/auth/signup`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        phone_number: phoneNumber,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(
        data.detail?.message ||
        data.message ||
        "Failed to send OTP."
        );
    }

    // Store phone number temporarily
    setSession({
      phone_number: phoneNumber,
    });

    go("otp");

  } catch (err) {
    console.error(err);

    if (setError) setError(err.message);

    alert(err.message || "Unable to connect to server.");
  } finally {
    setLoading(false);
  }
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
            Enter your registered phone number to begin your credit assessment.
            Your session is encrypted and expires in 60 minutes.
          </p>

          <div className="fade-up-3" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={{ fontSize: 13, fontWeight: 500, color: "var(--ink2)",
                display: "block", marginBottom: 8 }}>Phone Number</label>
              <input
                className="input-field"
                value={phone}
                onChange={e => setPhone(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleContinue()}
                placeholder="e.g. 9876543210"
                style={{ fontFamily: "'Syne', sans-serif", letterSpacing: "0.02em" }}
              />
              <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 6 }}>
                An OTP will be sent to this number for verification.
              </div>
            </div>

            <button className="btn-primary btn-orange"
              onClick={handleContinue} disabled={!phone.trim()}
              style={{ padding: "14px 28px", fontSize: 15, alignSelf: "flex-start" }}>
                {loading ? "Sending OTP..." : "Continue →"}
            </button>
          </div>

          {/* Trust signals */}
          <div className="fade-up-4" style={{ display: "flex", gap: 20, marginTop: 40,
            paddingTop: 28, borderTop: "1px solid var(--border)" }}>
            {[
              {label: "AES-256 encrypted" },
              {label: "DPDPA 2023 aligned" },
              {label: "60-min session" },
            ].map(({ icon, label }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 14 }}>{icon}</span>
                <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 500 }}>{label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right — visual */}
<div
  className="fade-up-2 dot-overlay"
  style={{
    position: "relative",
    height: 460,

    display: "flex",
    justifyContent: "center",
    alignItems: "center",

    overflow: "hidden",
  }}
>

  {/* ambient glow */}
  <div
    style={{
      position: "absolute",

      width: 320,
      height: 320,

      borderRadius: "50%",

      background:
        "radial-gradient(circle, rgba(255,170,120,0.22), rgba(180,120,255,0.16), transparent 72%)",

      filter: "blur(38px)",

      animation: "glowPulse 6s ease-in-out infinite",
    }}
  />

  {/* floating particles */}
  <div className="particle p1" />
  <div className="particle p2" />
  <div className="particle p3" />

  {/* prism */}
  <div className="prism-scene">

    <div className="prism">

      <div className="prism-face prism-front"></div>

      <div className="prism-face prism-left"></div>

      <div className="prism-face prism-right"></div>

      <div className="prism-shine"></div>

    </div>

  </div>
  </div>
      </div>
    </div>
  );
}