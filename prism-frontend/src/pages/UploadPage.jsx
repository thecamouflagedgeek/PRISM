// src/pages/UploadPage.jsx
import { useRef } from "react";
import { Nav } from "../components/Nav";

const BASE = import.meta.env.VITE_API_URL || "https://prism-backend-4mfu.onrender.com";

export default function UploadPage({ go, session, consents, files, setFiles, setResult, setError }) {

  const slots = [
    { key: "bank",    label: "Bank Statement",required: true,  enabled: consents.bank,
      desc: "Last 6–12 months. PDF format. Any Indian bank." },
    { key: "salary",  label: "Salary Slip",required: false, enabled: consents.salary,
      desc: "Last 3 months. Improves income verification." },
    { key: "utility", label: "Utility Bill",required: false, enabled: consents.utility,
      desc: "Electricity, water, or telecom. Any provider." },
  ];

  const canProceed = files.bank !== null;

  const handleSubmit=async() => {
    go("processing");
    try
    {
      if(!session?.id)
      {
        throw new Errow("Session not found. Please login again");
      }
      const form=new FormData();
      form.append("bank_file",files.bank);
      if(files.salary)
      {
        form.append("salary_file",files.salary);
      }
      if(files.utility)
      {
        form.append("utility_file",files.utility);
      }

      const res=await fetch(`${BASE}/assess`,{method:"POST",
        headers:{"session-id":session.id,},
        body:form,
      });
      const data=await res.json();
      if(!res.ok)
      {
        throw new Error(data.detail || data.message || "Assessment failed");
      }
      setResult(data);
      go("results");
    }
    catch(e) 
    {
      console.error("Assessment error",e);
      setError(e.message);
      go("upload");
    }
  };

  return (
    <div className="dot-grid" style={{ minHeight: "100vh" }}>
      <Nav currentPage="results" onLogoClick={() => {localStorage.clear(); go("landing");}}/>

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "64px 48px",
        display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: 80, alignItems: "start" }}>

        {/* Left */}
        <div style={{ position: "sticky", top: 96 }}>
          <div className="fade-up" style={{ fontSize: 12, fontWeight: 600, color: "var(--orange)",
            textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 12,
            fontFamily: "'Syne', sans-serif" }}>Step 3 of 4</div>
          <h1 className="display fade-up-1" style={{ fontSize: 44, color: "var(--ink)", marginBottom: 16 }}>
            Upload Your<br />
            <span style={{ color: "var(--orange)" }}>Documents.</span>
          </h1>
          <p className="fade-up-2" style={{ color: "var(--muted)", fontSize: 15, lineHeight: 1.7,
            fontWeight: 300, marginBottom: 32 }}>
            Documents are parsed locally and never stored permanently.
            Only fields required for scoring are extracted.
          </p>

          {/* Pipeline preview */}
          <div className="fade-up-3 card" style={{ padding: "20px 22px" }}>
            <div className="heading" style={{ fontSize: 13, color: "var(--muted)",
              textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 14 }}>
              What happens next
            </div>
            {[
              {label: "Parse",            sub: "pdfplumber / PyMuPDF" },
              {  label: "Validate",         sub: "Field confidence scoring" },
              { label: "Feature engineer", sub: "Cashflow, discipline, employment" },
              { label: "Score",            sub: "300–900 with SHAP reasons" },
            ].map(({ icon, label, sub }, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 12,
                padding: "8px 0",
                borderBottom: i < 3 ? "1px solid var(--border)" : "none" }}>
                <span style={{ fontSize: 16, width: 24 }}>{icon}</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>{label}</div>
                  <div style={{ fontSize: 11, color: "var(--muted)" }}>{sub}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="blob blob-purple"
            style={{ width: 80, height: 80, opacity: 0.2, marginTop: 28,
              animation: "float 6s 0.5s ease-in-out infinite" }} />
        </div>

        {/* Right — upload slots */}
        <div className="fade-up-2" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {slots.map(s => (
            <DropZone key={s.key} {...s}
              file={files[s.key]}
              onFile={f => setFiles(fs => ({ ...fs, [s.key]: f }))} />
          ))}

          {/* Summary */}
          <div style={{ padding: "14px 18px", borderRadius: 12,
            background: "var(--cream)", border: "1px solid var(--border)",
            fontSize: 13, color: "var(--muted)" }}>
            {Object.entries(files).filter(([, v]) => v).length} of {slots.filter(s => s.enabled).length}{" "}
            enabled documents uploaded
            {files.bank && " · Ready to assess"}
          </div>

          <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
            <button className="btn-outline" onClick={() => go("consent")} style={{ flex: "0 0 auto" }}>
              ← Back
            </button>
            <button className="btn-primary btn-orange"
              onClick={handleSubmit} disabled={!canProceed}
              style={{ flex: 1, justifyContent: "center", padding: "14px", fontSize: 15 }}>
              Run Assessment →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function DropZone({ key: _, label, icon, required, enabled, desc, file, onFile }) {
  const ref = useRef();
  const hasFile = file !== null;

  return (
    <div style={{ opacity: enabled ? 1 : 0.45, pointerEvents: enabled ? "auto" : "none" }}>
      <div className={`drop-zone ${hasFile ? "has-file" : ""} ${!enabled ? "disabled" : ""}`}
        onClick={() => enabled && ref.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); onFile(e.dataTransfer.files[0] || null); }}>

        <div style={{ display: "flex", alignItems: "center", gap: 16, textAlign: "left" }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, flexShrink: 0,
            background: hasFile ? "#DCFCE7" : "var(--white)",
            border: `1px solid ${hasFile ? "#86EFAC" : "var(--border)"}`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 22, transition: "all 0.2s" }}>
            {hasFile ? "✓" : icon}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
              <span style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)" }}>{label}</span>
              {required && (
                <span style={{ fontSize: 10, fontWeight: 600, padding: "1px 6px",
                  borderRadius: 50, background: "#FEE2E2", color: "#DC2626" }}>Required</span>
              )}
              {!enabled && (
                <span style={{ fontSize: 10, color: "var(--muted)" }}>· Consent not given</span>
              )}
            </div>
            <div style={{ fontSize: 12, color: hasFile ? "#16A34A" : "var(--muted)" }}>
              {hasFile ? file.name : desc}
            </div>
          </div>
          {hasFile && (
            <button onClick={e => { e.stopPropagation(); onFile(null); }}
              style={{ background: "none", border: "none", color: "var(--muted)",
                cursor: "pointer", fontSize: 18, padding: "4px" }}>✕</button>
          )}
        </div>

        {!hasFile && (
          <div style={{ marginTop: 10, fontSize: 11, color: "var(--muted)" }}>
            Click to browse or drag & drop · PDF only
          </div>
        )}
      </div>
      <input ref={ref} type="file" accept=".pdf" style={{ display: "none" }}
        onChange={e => e.target.files[0] && onFile(e.target.files[0])} />
    </div>
  );
}