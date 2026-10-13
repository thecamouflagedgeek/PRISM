import { useCallback, useEffect, useState } from "react";
import { api } from "./services/api";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import ConsentPage from "./pages/ConsentPage";
import UploadPage from "./pages/UploadPage";
import ProcessingPage from "./pages/ProcessingPage";
import ResultsPage from "./pages/ResultsPage";
import BorrowerDashboard from "./pages/BorrowerDashboard";
import OTPPage from "./pages/OTPPage";
import LenderLogin from "./pages/LenderLogin";
import LenderDashboard from "./pages/LenderDashboard";
import ApplicationsPage from "./pages/ApplicationsPage";
import AssessmentPage from "./pages/AssessmentPage";
import DocumentReview from "./pages/DocumentReview";
import FraudIntelligencePage from "./pages/FraudIntelligencePage";
import ExplainabilityPage from "./pages/ExplainabilityPage";
import AuditLogPage from "./pages/AuditLogPage";
import ExperimentalCreditEvidenceLab from "./pages/ExperimentalCreditEvidenceLab";
import DemonstrationPortal from "./pages/DemonstrationPortal";
import "./index.css";

export default function App() {
  const restoredSession = (() => { try { return JSON.parse(sessionStorage.getItem("prism_borrower_session") || "null"); } catch { return null; } })();
  const [page, setPage]       = useState(restoredSession ? "restoring" : "landing");
  const [session, setSessionState] = useState(restoredSession);   // short-lived authenticated session id
  const [consents, setConsents] = useState({
    bank: true, salary: false, utility: false,
    bureau: false, dpdpa: true,
  });
  const [files, setFiles]   = useState({ bank: null, salary: null, utility: null, creditCards: [] });
  const [result, setResultState] = useState(null);
  const [error,  setError]  = useState(null);
  const [assessmentInput, setAssessmentInput] = useState(null);
  const [lenderSession, setLenderSession] = useState(null);
  const [lenderAssessment, setLenderAssessment] = useState(null);
  const setSession = useCallback((value) => {
    if (!value || value.application_id !== session?.application_id) {
      sessionStorage.removeItem('prism_assessment_id');
      sessionStorage.removeItem('prism_bank_assessment_id');
      setResultState(null);
      setFiles({bankStatements: [], creditCards: [], salary: [], utility: [], bank: null});
      setAssessmentInput(null);
    }
    setSessionState(value);
    if (value?.session_id) sessionStorage.setItem("prism_borrower_session", JSON.stringify(value));
    else sessionStorage.removeItem("prism_borrower_session");
  }, [session?.application_id]);
  const setResult = (value) => {
    setResultState(value);
    if (value?.assessment_id && value.assessment_type !== "BANK_CASHFLOW_EXPERIMENTAL") sessionStorage.setItem("prism_assessment_id", value.assessment_id);
    else sessionStorage.removeItem("prism_assessment_id");
    const bankId = value?.assessment_type === "BANK_CASHFLOW_EXPERIMENTAL" ? value.assessment_id : value?.bank_cashflow_assessment?.assessment_id;
    if (bankId) sessionStorage.setItem("prism_bank_assessment_id", bankId);
    else sessionStorage.removeItem("prism_bank_assessment_id");
  };
  useEffect(() => {
    if (page !== "restoring" || !restoredSession?.session_id) return;
    let cancelled = false;
    Promise.allSettled([api.borrowerConsent(restoredSession.session_id), api.borrowerBankHistory(restoredSession.session_id)])
      .then(([consentResult, historyResult]) => {
        if (cancelled) return;
        if (consentResult.status === 'fulfilled') setConsents(consentResult.value);
        const authenticationError = [consentResult, historyResult].find(item =>
          item.status === 'rejected' && item.reason?.status === 401);
        if (authenticationError) {
          sessionStorage.removeItem("prism_borrower_session");
          sessionStorage.removeItem("prism_assessment_id");
          sessionStorage.removeItem("prism_bank_assessment_id");
          setSessionState(null); setPage("landing"); return;
        }
        const history = historyResult.status === 'fulfilled' ? historyResult.value : null;
        const latest = history?.assessments?.find(item => item.assessment_type === 'BANK_CASHFLOW_EXPERIMENTAL');
        if (history?.assessment_count) { if (latest) setResultState(latest); setPage('dashboard'); }
        else if (consentResult.status === 'fulfilled') setPage('upload');
        else setPage('consent');
      });
    return () => { cancelled = true; };
  }, [page, restoredSession?.session_id]);
  const go = useCallback((p) => {
    if (p === 'landing') {
      setSession(null); setLenderSession(null);
      setFiles({ bankStatements: [], creditCards: [], salary: [], utility: [] });
      setAssessmentInput(null);
    }
    setError(null); setPage(p);
  }, [setSession, setLenderSession, setFiles, setAssessmentInput, setError, setPage]);

  if (window.location.pathname === "/experimental-credit-evidence-lab") {
    return <ExperimentalCreditEvidenceLab />;
  }
  if (window.location.pathname === "/demo") return <DemonstrationPortal />;
  if (page === "restoring") return <main role="status" style={{ padding: 48 }}>Loading your saved assessment…</main>;

  const props = {
    session, setSession, consents, setConsents,
    files, setFiles, result, setResult,
    error, setError, go, assessmentInput, setAssessmentInput,
    lenderSession, setLenderSession, lenderAssessment, setLenderAssessment,
  };

  return (
    <div className="app-root">
      {page === "landing"    && <LandingPage    {...props} />}
      {page === "login"      && <LoginPage      {...props} />}
      {page === "otp" && <OTPPage {...props} />}
      {page === "consent"    && <ConsentPage    {...props} />}
      {page === "upload"     && <UploadPage     {...props} />}
      {page === "processing" && <ProcessingPage {...props} />}
      {page === "results"    && <ResultsPage    {...props} />}
      {page === "dashboard"  && <BorrowerDashboard {...props} />}
      {page === "lenderLogin" && <LenderLogin {...props} />}
      {page === "lenderDashboard" && <LenderDashboard {...props} />}
      {page === "applications" && <ApplicationsPage {...props} />}
      {page === "assessment" && <AssessmentPage {...props} />}
      {page === "documentReview" && <DocumentReview {...props} />}
      {page === "fraudIntelligence" && <FraudIntelligencePage {...props} />}
      {page === "explainability" && <ExplainabilityPage {...props} />}
      {page === "auditLog" && <AuditLogPage {...props} />}
    </div>
  );
}
