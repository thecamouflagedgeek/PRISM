import { useState } from "react";
import { Nav } from "../components/Nav";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function OTPPage({ go, session, setSession, setError }) {
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);

  const verifyOTP = async () => {
    if (!otp.trim() || loading) return;

    setLoading(true);

    try {
      const res = await fetch(`${API}/auth/verify`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          phone_number: session.phone_number,
          otp: otp.trim(),
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(
        data.detail?.message ||
        data.message ||
        "OTP verification failed"
        );
      }

      setSession({
        ...session,
        session_id: data.session_id,
        application_id: data.application_id,
      });

      go("consent");
    } catch (err) {
      console.error(err);

      if (setError) setError(err.message);

      alert(err.message || "OTP verification failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dot-grid" style={{ minHeight: "100vh" }}>
      <Nav currentPage="login" onLogoClick={() => go("landing")} />

      <div
        style={{
          maxWidth: 600,
          margin: "0 auto",
          padding: "80px 40px",
        }}
      >
        <div
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: "var(--orange)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
            marginBottom: 12,
          }}
        >
          Step 2 of 5
        </div>

        <h1
          className="display"
          style={{
            fontSize: 46,
            color: "var(--ink)",
            marginBottom: 14,
          }}
        >
          Verify OTP
        </h1>

        <p
          style={{
            color: "var(--muted)",
            marginBottom: 35,
            lineHeight: 1.6,
          }}
        >
          Enter the OTP sent to
          <br />
          <strong>{session?.phone_number}</strong>
        </p>

        <label
          style={{
            fontSize: 13,
            fontWeight: 500,
            marginBottom: 8,
            display: "block",
          }}
        >
          OTP
        </label>

        <input
          className="input-field"
          value={otp}
          onChange={(e) => setOtp(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && verifyOTP()}
          placeholder="Enter 6-digit OTP"
        />

        <button
          className="btn-primary btn-orange"
          style={{
            marginTop: 25,
            padding: "14px 30px",
          }}
          disabled={!otp.trim() || loading}
          onClick={verifyOTP}
        >
          {loading ? "Verifying..." : "Verify OTP →"}
        </button>
      </div>
    </div>
  );
}