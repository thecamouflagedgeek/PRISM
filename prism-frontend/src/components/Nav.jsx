import { useLanguage } from "../components/LanguageContext";

const STEPS = [
  { key: "login", label: "Login" },
  { key: "consent", label: "Consent" },
  { key: "upload", label: "Upload" },
  { key: "results", label: "Results" },
];

export function Nav({ currentPage, onLogoClick, onLogout }) {
  const stepKeys = STEPS.map((s) => s.key);

  const { language, toggleLanguage } = useLanguage();

  const currentIdx = stepKeys.indexOf(
    currentPage === "processing" ? "upload" : currentPage
  );

  return (
    <nav className="nav">
      {/* Logo */}
      <div
        className="nav-logo"
        onClick={onLogoClick}
        style={{ cursor: "pointer" }}
      >
        <div className="nav-logo-dot" />
        PRISM
      </div>

      {/* Step Progress */}
      {currentPage !== "landing" && (
        <div className="step-bar">
          {STEPS.map((step, i) => {
            const state =
              i < currentIdx
                ? "done"
                : i === currentIdx
                ? "active"
                : "future";

            return (
              <div
                key={step.key}
                style={{ display: "flex", alignItems: "center" }}
              >
                <div className="step-item">
                  <div className={`step-circle ${state}`}>
                    {state === "done" ? "✓" : i + 1}
                  </div>

                  <span className={`step-label ${state}`}>
                    {step.label}
                  </span>
                </div>

                {i < STEPS.length - 1 && (
                  <div
                    className={`step-line ${
                      state === "done" ? "done" : ""
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Right Side Controls */}
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        
        {/* Landing Page Buttons */}
        {currentPage === "landing" && (
          <>
            <button
              className="btn-outline"
              style={{
                fontSize: 13,
                padding: "8px 18px",
              }}
            >
              Login
            </button>

            <button
              className="btn-primary btn-orange"
              style={{
                fontSize: 13,
                padding: "8px 18px",
              }}
            >
              Get Started
            </button>
          </>
        )}

        {/* Results Page Logout Button */}
        {currentPage === "results" && (
          <button
            className="btn-outline"
            onClick={onLogout}
            style={{
              fontSize: 13,
              padding: "8px 18px",
            }}
          >
            Logout
          </button>
        )}

        {/* Language Toggle */}
        <button
          onClick={toggleLanguage}
          className="btn-outline"
          style={{
            fontSize: 12,
            padding: "8px 14px",
          }}
        >
          {language === "en" ? "हिंदी" : "English"}
        </button>

        {/* Secure Session */}
        {currentPage !== "landing" && (
          <div
            style={{
              fontSize: 12,
              color: "var(--muted)",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <div
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "var(--green)",
              }}
            />
            Secure session
          </div>
        )}
      </div>
    </nav>
  );
}