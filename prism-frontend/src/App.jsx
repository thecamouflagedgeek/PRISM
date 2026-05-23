import { useState } from "react";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import ConsentPage from "./pages/ConsentPage";
import UploadPage from "./pages/UploadPage";
import ProcessingPage from "./pages/ProcessingPage";
import ResultsPage from "./pages/ResultsPage";
import "./index.css";

export default function App() {
  const [page, setPage]       = useState("landing");
  const [session, setSession] = useState(null);   // { id, borrowerId }
  const [consents, setConsents] = useState({
    bank: true, salary: false, utility: false,
    bureau: false, dpdpa: true,
  });
  const [files, setFiles]   = useState({ bank: null, salary: null, utility: null });
  const [result, setResult] = useState(null);
  const [error,  setError]  = useState(null);

  const go = (p) => { setError(null); setPage(p); };

  const props = {
    session, setSession, consents, setConsents,
    files, setFiles, result, setResult,
    error, setError, go,
  };

  return (
    <div className="app-root">
      {page === "landing"    && <LandingPage    {...props} />}
      {page === "login"      && <LoginPage      {...props} />}
      {page === "consent"    && <ConsentPage    {...props} />}
      {page === "upload"     && <UploadPage     {...props} />}
      {page === "processing" && <ProcessingPage {...props} />}
      {page === "results"    && <ResultsPage    {...props} />}
    </div>
  );
}