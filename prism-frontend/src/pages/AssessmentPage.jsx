import { Nav } from "../components/Nav";

export default function AssessmentPage({ go, lenderSession }) {
  // --------------------------------------------------
  // MOCK ASSESSMENT DATA
  // Replace with lender-side API response later
  // --------------------------------------------------
  const assessment = {
    application_id: "PR-1022",
    borrower_id: "BR-0037",

    risk_score: 364,
    probability_of_default: 57.9,
    risk_tier: "High Risk",
    confidence: 68.7,

    documents: {
      bank_statement: "Verified",
      salary_slip: "Verified",
      utility_bill: "Pending",
    },

    fraud_flags: 0,

    factor_contributions: [
      {
        feature: "Utility Payment Discipline",
        contribution: -56.7,
        direction: "Negative",
        evidence: "Frequent payment delays",
      },
      {
        feature: "Cashflow Volatility",
        contribution: 20.4,
        direction: "Positive",
        evidence: "Moderate monthly variation",
      },
      {
        feature: "Income Stability",
        contribution: 6.8,
        direction: "Positive",
        evidence: "Consistent salary credits",
      },
      {
        feature: "Average Balance",
        contribution: 4.9,
        direction: "Positive",
        evidence: "Stable average balance",
      },
      {
        feature: "Credit-Debit Ratio",
        contribution: 0.0,
        direction: "Neutral",
        evidence: "No significant impact",
      },
    ],

    reason_codes: [
      "Utility payment delays",
      "Elevated probability of default",
      "Moderate cashflow volatility",
    ],
  };

  // --------------------------------------------------
  // STYLES
  // --------------------------------------------------
  const riskStyle = {
    background: "rgba(220, 70, 70, 0.10)",
    color: "#b33a3a",
  };

  const getContributionStyle = (value) => {
    if (value < 0) {
      return {
        color: "#b33a3a",
        background: "rgba(220, 70, 70, 0.08)",
      };
    }

    if (value > 0) {
      return {
        color: "#287a3d",
        background: "rgba(52, 168, 83, 0.08)",
      };
    }

    return {
      color: "var(--muted)",
      background: "rgba(100, 100, 100, 0.08)",
    };
  };

  return (
    <div
      className="dot-grid"
      style={{
        minHeight: "100vh",
        backgroundColor: "var(--bg)",
      }}
    >
      {/* --------------------------------------------- */}
      {/* NAV */}
      {/* --------------------------------------------- */}
      <Nav
        currentPage="assessment"
        onLogoClick={() => go("landing")}
      />

      <main
        style={{
          maxWidth: 1200,
          margin: "0 auto",
          padding: "50px 40px 80px",
        }}
      >
        {/* ------------------------------------------- */}
        {/* BACK + HEADER */}
        {/* ------------------------------------------- */}
        <div
          className="fade-up"
          style={{
            marginBottom: 30,
          }}
        >
          <button
            onClick={() => go("applications")}
            style={{
              border: "none",
              background: "transparent",
              padding: 0,
              color: "var(--muted)",
              cursor: "pointer",
              fontSize: 12,
              marginBottom: 18,
            }}
          >
            ← Applications
          </button>

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-end",
              gap: 30,
            }}
          >
            <div>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--orange)",
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                  marginBottom: 10,
                  fontFamily: "'Syne', sans-serif",
                }}
              >
                Assessment Workspace
              </div>

              <h1
                className="display"
                style={{
                  fontSize: 42,
                  color: "var(--ink)",
                  margin: 0,
                }}
              >
                {assessment.application_id}
              </h1>

              <p
                style={{
                  marginTop: 9,
                  color: "var(--muted)",
                  fontSize: 13,
                }}
              >
                Borrower {assessment.borrower_id}
              </p>
            </div>

            <span
              style={{
                ...riskStyle,
                padding: "8px 14px",
                borderRadius: 20,
                fontSize: 11,
                fontWeight: 600,
              }}
            >
              {assessment.risk_tier}
            </span>
          </div>
        </div>

        {/* ------------------------------------------- */}
        {/* TOP RISK SUMMARY */}
        {/* ------------------------------------------- */}
        <div
          className="fade-up-1"
          style={{
            display: "grid",
            gridTemplateColumns: "1.2fr 1fr 1fr 1fr",
            gap: 14,
            marginBottom: 20,
          }}
        >
          {/* Credit Score */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: 24,
            }}
          >
            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                textTransform: "uppercase",
                letterSpacing: "0.07em",
                marginBottom: 12,
              }}
            >
              PRISM Credit Score
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: 6,
              }}
            >
              <span
                style={{
                  fontFamily: "'Syne', sans-serif",
                  fontSize: 42,
                  fontWeight: 600,
                  color: "var(--ink)",
                }}
              >
                {assessment.risk_score}
              </span>

              <span
                style={{
                  fontSize: 12,
                  color: "var(--muted)",
                }}
              >
                / 900
              </span>
            </div>

            <div
              style={{
                marginTop: 14,
                height: 6,
                background: "var(--border)",
                borderRadius: 10,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${(assessment.risk_score / 900) * 100}%`,
                  height: "100%",
                  background: "#b33a3a",
                  borderRadius: 10,
                }}
              />
            </div>
          </div>

          {/* PD */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: 24,
            }}
          >
            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                textTransform: "uppercase",
                letterSpacing: "0.07em",
                marginBottom: 12,
              }}
            >
              Probability of Default
            </div>

            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 34,
                fontWeight: 600,
                color: "var(--ink)",
              }}
            >
              {assessment.probability_of_default}%
            </div>

            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                marginTop: 7,
              }}
            >
              Estimated default probability
            </div>
          </div>

          {/* Confidence */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: 24,
            }}
          >
            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                textTransform: "uppercase",
                letterSpacing: "0.07em",
                marginBottom: 12,
              }}
            >
              Model Confidence
            </div>

            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 34,
                fontWeight: 600,
                color: "var(--ink)",
              }}
            >
              {assessment.confidence}%
            </div>

            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                marginTop: 7,
              }}
            >
              Confidence in assessment
            </div>
          </div>

          {/* Fraud */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: 24,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                gap: 16,
              }}
            >
              <div>
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.07em",
                    marginBottom: 12,
                  }}
                >
                  Fraud Flags
                </div>

                <div
                  style={{
                    fontFamily: "'Syne', sans-serif",
                    fontSize: 34,
                    fontWeight: 600,
                    color: "#287a3d",
                  }}
                >
                  {assessment.fraud_flags}
                </div>

                <div
                  style={{
                    fontSize: 11,
                    color: "var(--muted)",
                    marginTop: 7,
                  }}
                >
                  Detected anomalies
                </div>
              </div>

              {/* Fraud Intelligence button */}
              <button
                className="btn-outline"
                onClick={() => go("fraudIntelligence")}
                style={{
                  padding: "9px 14px",
                  fontSize: 12,
                  whiteSpace: "nowrap",
                }}
              >
                Fraud Intelligence →
              </button>
            </div>
          </div>
        </div>

        {/* ------------------------------------------- */}
        {/* MAIN CONTENT */}
        {/* ------------------------------------------- */}
        <div
          className="fade-up-2"
          style={{
            display: "grid",
            gridTemplateColumns: "1.35fr 0.65fr",
            gap: 20,
            alignItems: "start",
          }}
        >
          {/* ----------------------------------------- */}
          {/* FACTOR CONTRIBUTIONS */}
          {/* ----------------------------------------- */}
          <section
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "22px 24px",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <h2
                style={{
                  margin: 0,
                  fontSize: 17,
                  color: "var(--ink)",
                  fontFamily: "'Syne', sans-serif",
                }}
              >
                Assessment Factors
              </h2>

              <p
                style={{
                  margin: "5px 0 0",
                  fontSize: 12,
                  color: "var(--muted)",
                }}
              >
                Factors contributing to the generated score
              </p>
            </div>

            {assessment.factor_contributions.map((factor) => (
              <div
                key={factor.feature}
                style={{
                  padding: "19px 24px",
                  borderBottom: "1px solid var(--border)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 20,
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: "var(--ink)",
                      }}
                    >
                      {factor.feature}
                    </div>

                    <div
                      style={{
                        fontSize: 11,
                        color: "var(--muted)",
                        marginTop: 5,
                      }}
                    >
                      {factor.evidence}
                    </div>
                  </div>

                  <span
                    style={{
                      ...getContributionStyle(factor.contribution),
                      padding: "6px 10px",
                      borderRadius: 20,
                      fontSize: 11,
                      fontWeight: 600,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {factor.contribution > 0 ? "+" : ""}
                    {factor.contribution} pts
                  </span>
                </div>
              </div>
            ))}
          </section>

          {/* ----------------------------------------- */}
          {/* RIGHT PANEL */}
          {/* ----------------------------------------- */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 20,
            }}
          >
            {/* Reason Codes */}
            <section
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: 14,
                padding: 24,
              }}
            >
              <h2
                style={{
                  margin: 0,
                  fontSize: 17,
                  color: "var(--ink)",
                  fontFamily: "'Syne', sans-serif",
                }}
              >
                Key Reasons
              </h2>

              <p
                style={{
                  margin: "5px 0 20px",
                  fontSize: 12,
                  color: "var(--muted)",
                }}
              >
                Primary drivers identified by PRISM
              </p>

              {assessment.reason_codes.map((reason, index) => (
                <div
                  key={reason}
                  style={{
                    display: "flex",
                    gap: 10,
                    alignItems: "flex-start",
                    marginBottom:
                      index === assessment.reason_codes.length - 1
                        ? 0
                        : 14,
                  }}
                >
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      minWidth: 6,
                      borderRadius: "50%",
                      background: "var(--orange)",
                      marginTop: 5,
                    }}
                  />

                  <span
                    style={{
                      fontSize: 12,
                      lineHeight: 1.5,
                      color: "var(--ink2)",
                    }}
                  >
                    {reason}
                  </span>
                </div>
              ))}
            </section>

            {/* Documents */}
            <section
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: 14,
                padding: 24,
              }}
            >
              <h2
                style={{
                  margin: 0,
                  fontSize: 17,
                  color: "var(--ink)",
                  fontFamily: "'Syne', sans-serif",
                }}
              >
                Documents
              </h2>

              <p
                style={{
                  margin: "5px 0 20px",
                  fontSize: 12,
                  color: "var(--muted)",
                }}
              >
                Verification status
              </p>

              {Object.entries(assessment.documents).map(
                ([document, status]) => (
                  <div
                    key={document}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "11px 0",
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <span
                      style={{
                        fontSize: 12,
                        color: "var(--ink2)",
                        textTransform: "capitalize",
                      }}
                    >
                      {document.replaceAll("_", " ")}
                    </span>

                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 600,
                        color:
                          status === "Verified"
                            ? "#287a3d"
                            : "var(--orange)",
                      }}
                    >
                      {status}
                    </span>
                  </div>
                )
              )}

              <button
                className="btn-outline"
                onClick={() => go("documentReview")}
                style={{
                  width: "100%",
                  padding: "11px",
                  marginTop: 18,
                  fontSize: 12,
                }}
              >
                Review Documents →
              </button>
            </section>

            {/* Explainability */}
            <section
              style={{
                background: "var(--ink)",
                borderRadius: 14,
                padding: 24,
                color: "white",
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  opacity: 0.6,
                  marginBottom: 10,
                }}
              >
                Explainability
              </div>

              <div
                style={{
                  fontSize: 15,
                  fontWeight: 600,
                  marginBottom: 8,
                }}
              >
                Understand the assessment
              </div>

              <div
                style={{
                  fontSize: 11,
                  lineHeight: 1.6,
                  opacity: 0.65,
                  marginBottom: 18,
                }}
              >
                Review feature-level contributions and the factors influencing
                this assessment.
              </div>

              <button
                onClick={() => go("explainability")}
                style={{
                  border: "1px solid rgba(255,255,255,0.25)",
                  background: "transparent",
                  color: "white",
                  borderRadius: 8,
                  padding: "9px 13px",
                  cursor: "pointer",
                  fontSize: 11,
                }}
              >
                View Explainability →
              </button>
            </section>
          </div>
        </div>

        {/* ------------------------------------------- */}
        {/* FOOTER ACTIONS */}
        {/* ------------------------------------------- */}
        <div
          className="fade-up-3"
          style={{
            marginTop: 22,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 15,
          }}
        >
          <span
            style={{
              fontSize: 11,
              color: "var(--muted)",
            }}
          >
            Assessment generated by the PRISM risk scoring pipeline.
          </span>

          <button
            className="btn-outline"
            onClick={() => go("applications")}
            style={{
              padding: "10px 16px",
              fontSize: 11,
            }}
          >
            ← Back to Applications
          </button>
        </div>
      </main>
    </div>
  );
}