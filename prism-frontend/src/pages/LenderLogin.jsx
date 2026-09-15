// src/pages/LenderLogin.jsx
import { useState } from "react";
import { Nav } from "../components/Nav";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function LenderLogin({ go, setLenderSession, setError }) {
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

      // Store lender session temporarily
      setLenderSession({
        phone_number: phoneNumber,
        role: "lender",
      });

      // Reuse existing OTP page
      go("otp");

    } catch (err) {
      console.error(err);

      if (setError) {
        setError(err.message);
      }

      alert(err.message || "Unable to connect to server.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dot-grid" style={{ minHeight: "100vh" }}>
      <Nav
        currentPage="lenderLogin"
        onLogoClick={() => go("landing")}
      />

      <div
        style={{
          maxWidth: 1100,
          margin: "0 auto",
          padding: "72px 48px",
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 80,
          alignItems: "center",
        }}
      >

        {/* ───────────────── Left — form ───────────────── */}
        <div>

          <div
            className="fade-up"
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "var(--orange)",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              marginBottom: 12,
              fontFamily: "'Syne', sans-serif",
            }}
          >
            Lender Portal
          </div>

          <h1
            className="display fade-up-1"
            style={{
              fontSize: 48,
              color: "var(--ink)",
              marginBottom: 12,
            }}
          >
            Welcome to<br />
            <span style={{ color: "var(--orange)" }}>PRISM.</span>
          </h1>

          <p
            className="fade-up-2"
            style={{
              color: "var(--muted)",
              fontSize: 16,
              lineHeight: 1.65,
              fontWeight: 300,
              marginBottom: 40,
              maxWidth: 430,
            }}
          >
            Sign in to review borrower applications, risk assessments,
            document insights and explainable credit decisions.
          </p>

          <div
            className="fade-up-3"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 16,
            }}
          >

            {/* Phone Number */}
            <div>
              <label
                style={{
                  fontSize: 13,
                  fontWeight: 500,
                  color: "var(--ink2)",
                  display: "block",
                  marginBottom: 8,
                }}
              >
                Phone Number
              </label>

              <input
                className="input-field"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                onKeyDown={(e) =>
                  e.key === "Enter" && handleContinue()
                }
                placeholder="e.g. 9876543210"
                style={{
                  fontFamily: "'Syne', sans-serif",
                  letterSpacing: "0.02em",
                }}
              />

              <div
                style={{
                  fontSize: 12,
                  color: "var(--muted)",
                  marginTop: 6,
                }}
              >
                An OTP will be sent to this number for verification.
              </div>
            </div>

            {/* Continue */}
            <button
              className="btn-primary btn-orange"
              onClick={handleContinue}
              disabled={!phone.trim() || loading}
              style={{
                padding: "14px 28px",
                fontSize: 15,
                alignSelf: "flex-start",
              }}
            >
              {loading ? "Sending OTP..." : "Continue →"}
            </button>
          </div>

          {/* Trust signals */}
          <div
            className="fade-up-4"
            style={{
              display: "flex",
              gap: 20,
              marginTop: 40,
              paddingTop: 28,
              borderTop: "1px solid var(--border)",
              flexWrap: "wrap",
            }}
          >
            {[
              { label: "Role-based access" },
              { label: "Secure authentication" },
              { label: "Audit-ready assessments" },
            ].map(({ label }) => (
              <div
                key={label}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <span
                  style={{
                    width: 5,
                    height: 5,
                    borderRadius: "50%",
                    background: "var(--orange)",
                  }}
                />

                <span
                  style={{
                    fontSize: 12,
                    color: "var(--muted)",
                    fontWeight: 500,
                  }}
                >
                  {label}
                </span>
              </div>
            ))}
          </div>

          {/* Back */}
          <button
            className="btn-outline"
            onClick={() => go("landing")}
            style={{
              marginTop: 24,
              padding: "10px 18px",
              fontSize: 13,
            }}
          >
            ← Back to PRISM
          </button>

        </div>


        {/* ───────────────── Right — visual ───────────────── */}
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

          {/* lender label */}
          <div
            style={{
              position: "absolute",
              bottom: 42,
              left: "50%",
              transform: "translateX(-50%)",
              fontSize: 11,
              color: "var(--muted)",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              fontFamily: "'Syne', sans-serif",
              whiteSpace: "nowrap",
            }}
          >
            Risk Intelligence · Explainability · Audit
          </div>

        </div>
      </div>
    </div>
  );
}