import { useState } from "react";

import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import ConsentPage from "./pages/ConsentPage";
import UploadPage from "./pages/UploadPage";
import ProcessingPage from "./pages/ProcessingPage";
import OTPPage from "./pages/OTPPage";
import ResultsPage from "./pages/ResultsPage";
import LenderLogin from "./pages/LenderLogin";
import LenderDashboard from "./pages/LenderDashboard";
import ApplicationsPage from "./pages/ApplicationsPage";
import AssessmentPage from "./pages/AssessmentPage";
import DocumentReview from "./pages/DocumentReview";
import FraudIntelligencePage from "./pages/FraudIntelligencePage";
import ExplainabilityPage from "./pages/ExplainabilityPage";
import AuditLogPage from "./pages/AuditLogPage";

import "./index.css";

export default function App() {
  // -----------------------------
  // BORROWER FLOW
  // -----------------------------
  const [page, setPage] = useState("landing");

  const [session, setSession] = useState(null);
  const [consents, setConsents] = useState({
    bank: true,
    salary: false,
    utility: false,
    bureau: false,
    dpdpa: true,
  });

  const [files, setFiles] = useState({
    bank: null,
    salary: null,
    utility: null,
  });

  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [assessmentInput, setAssessmentInput] = useState(null);

  // -----------------------------
  // LENDER FLOW
  // -----------------------------
  const [lenderSession, setLenderSession] = useState(null);
  const [lenderAssessment, setLenderAssessment] = useState(null);

  const go = (p) => {
    setError(null);
    setPage(p);
  };

  // -----------------------------
  // SHARED PROPS
  // -----------------------------
  const props = {
    session,
    setSession,

    consents,
    setConsents,

    files,
    setFiles,

    result,
    setResult,
    assessmentInput,
    setAssessmentInput,

    error,
    setError,

    go,

    lenderSession,
    setLenderSession,
    lenderAssessment,
    setLenderAssessment,
  };

  return (
    <div className="app-root">

      {/* =========================
          BORROWER FLOW
          ========================= */}

      {page === "landing" && (
        <LandingPage {...props} />
      )}

      {page === "login" && (
        <LoginPage {...props} />
      )}

      {page === "otp" && (
        <OTPPage {...props} />
      )}

      {page === "consent" && (
        <ConsentPage {...props} />
      )}

      {page === "upload" && (
        <UploadPage {...props} />
      )}

      {page === "processing" && (
        <ProcessingPage {...props} />
      )}

      {page === "results" && (
        <ResultsPage {...props} />
      )}

      {/* =========================
          LENDER FLOW
          ========================= */}

      {page === "lenderLogin" && <LenderLogin {...props} />}

      {page === "lenderDashboard" && (
  <LenderDashboard {...props} />
)}

      {page === "applications" && (
  <ApplicationsPage {...props} />
)}

      {page === "assessment" && (
  <AssessmentPage {...props} />
)}

{page === "documentReview" && (
  <DocumentReview {...props} />
)}

{page === "fraudIntelligence" && (
  <FraudIntelligencePage {...props} />
)}

{page === "explainability" && (
  <ExplainabilityPage {...props} />
)}

{page === "auditLog" && (
  <AuditLogPage {...props} />
)}

    </div>
  );
}
