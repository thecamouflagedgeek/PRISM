// src/pages/ProcessingPage.jsx
import { useEffect } from "react";
import { api } from "../services/api";
import { runAssessment } from "../services/assessmentWorkflow";

export default function ProcessingPage({ assessmentInput, setResult, setError, go }) {
  useEffect(() => {
    let cancelled = false;
    if (!assessmentInput) { setError("No documents were selected for assessment."); go("upload"); return undefined; }
    runAssessment(assessmentInput, api).then((data) => {
      if (!cancelled) { setResult(data); go("dashboard"); }
    }).catch((err) => {
      if (!cancelled) {
        if (assessmentInput.bankFirst) {
          go(err.status === 401 ? 'login' : 'upload');
          setError(err.message);
          return;
        }
        setResult({ status: err.status === 401 || err.status === 403 ? "AUTHENTICATION_REQUIRED" : err.status === 408 ? "TIMED_OUT" : "PROCESSING_ERROR", scoreable: false,
          model_validation_status: "NOT_RUN",
          data_sufficiency: { reasons: ["DOCUMENT_PROCESSING_NEEDS_REVIEW"], message: err.message },
          processing_error: err.message,
          assessed_at: new Date().toISOString() });
        go("results");
      }
    });
    return () => { cancelled = true; };
  }, [assessmentInput, go, setError, setResult]);

  return (
    <div className="dot-grid" style={{ minHeight: "100vh", display: "flex",
      flexDirection: "column", alignItems: "center", justifyContent: "center",
      padding: "48px 24px" }}>

      <div style={{ maxWidth: 560, width: "100%" }}>
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <div style={{ position: "relative", width: 72, height: 72, margin: "0 auto 20px" }}>
            <div style={{ width: 72, height: 72, borderRadius: "50%",
              border: "3px solid var(--border)", position: "absolute" }} />
            <div style={{ width: 72, height: 72, borderRadius: "50%",
              border: "3px solid var(--orange)", position: "absolute",
              borderRightColor: "transparent",
              animation: "spin-slow 1s linear infinite" }} />
            <span style={{ position: "absolute", inset: 0, display: "flex",
              alignItems: "center", justifyContent: "center", fontSize: 28 }}>P</span>
          </div>
        <h1 className="heading" style={{ fontSize: 28, color: "var(--ink)", marginBottom: 6 }}>
            Processing your documents
          </h1>
          <p style={{ color: "var(--muted)", fontSize: 14 }}>
            We are reading your bank transactions, checking the balances and calculating your cash-flow score. Optional documents are reviewed separately.
          </p>
        </div>
        <div className="card" role="status" style={{ padding: 22, display: "flex", alignItems: "center", gap: 14 }}>
          <span aria-hidden="true" style={{ width: 26, height: 26, flex: "0 0 26px", borderRadius: "50%", border: "3px solid var(--border)", borderTopColor: "var(--orange)", animation: "spin-slow 1s linear infinite" }} />
          <div><strong>Preparing your financial picture</strong><div style={{ marginTop: 4, fontSize: 13, color: "var(--muted)" }}>A single readable bank statement is enough to begin. Your report will show the period and patterns actually observed.</div></div>
        </div>
      </div>
    </div>
  );
}
