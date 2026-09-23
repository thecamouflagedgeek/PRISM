import { Nav } from "../components/Nav";

export default function ExplainabilityPage({ go, lenderSession, result, lenderAssessment }) {
  const credit = lenderAssessment?.credit_risk ?? result?.credit_risk ?? result ?? {};
  const assessment = {
    risk_score: credit.risk_score ?? "—",
    probability_of_default: credit.probability_of_default == null ? "—" : `${(Number(credit.probability_of_default) * 100).toFixed(1)}`,
    risk_tier: credit.risk_tier ?? "Unavailable",
    confidence: credit.confidence?.confidence_pct ?? credit.confidence ?? "—",
    factor_contributions: (credit.shap_explanations ?? []).map((item) => ({
      feature: item.feature_name ?? item.factor ?? "Feature",
      contribution: Number(item.score_contribution ?? 0),
      direction: item.contribution_type ?? (Number(item.score_contribution) === 0 ? "Neutral" : Number(item.score_contribution) > 0 ? "Positive" : "Negative"),
      evidence: item.generated_reason ?? item.reason ?? "Backend-provided score contribution",
    })),
    reason_codes: (credit.reason_codes ?? []).map((reason) => typeof reason === "string" ? reason : reason.message ?? reason.reason ?? reason.factor ?? "Assessment factor"),
  };

  const getDirectionStyle = (direction) => {
    if (direction === "Negative") {
      return {
        color: "#b33a3a",
        background: "rgba(220, 70, 70, 0.10)",
      };
    }

    if (direction === "Positive") {
      return {
        color: "#287a3d",
        background: "rgba(52, 168, 83, 0.10)",
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
      <Nav
        currentPage="explainability"
        onLogoClick={() => go("landing")}
      />

      <main
        style={{
          maxWidth: 1200,
          margin: "0 auto",
          padding: "50px 40px 80px",
        }}
      >
        {/* Back */}
        <button
          onClick={() => go("assessment")}
          style={{
            border: "none",
            background: "transparent",
            padding: 0,
            color: "var(--muted)",
            cursor: "pointer",
            fontSize: 12,
            marginBottom: 24,
          }}
        >
          ← Back to Assessment
        </button>

        {/* Header */}
        <div
          className="fade-up"
          style={{
            marginBottom: 30,
          }}
        >
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
            Explainability
          </div>

          <h1
            className="display"
            style={{
              fontSize: 42,
              color: "var(--ink)",
              margin: 0,
            }}
          >
            Why this assessment?
          </h1>

          <p
            style={{
              marginTop: 9,
              color: "var(--muted)",
              fontSize: 13,
            }}
          >
            Application {assessment.application_id} · Borrower{" "}
            {assessment.borrower_id}
          </p>
        </div>

        {/* Assessment summary */}
        <div
          className="fade-up-1"
          style={{
            display: "grid",
            gridTemplateColumns: "1.3fr 1fr 1fr 1fr",
            gap: 14,
            marginBottom: 24,
          }}
        >
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
                marginBottom: 10,
              }}
            >
              PRISM Credit Score
            </div>

            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 40,
                fontWeight: 600,
                color: "var(--ink)",
              }}
            >
              {assessment.risk_score}
              <span
                style={{
                  fontSize: 12,
                  color: "var(--muted)",
                  marginLeft: 5,
                }}
              >
                / 900
              </span>
            </div>
          </div>

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
                marginBottom: 10,
              }}
            >
              Probability of Default
            </div>

            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 32,
                fontWeight: 600,
                color: "var(--ink)",
              }}
            >
              {assessment.probability_of_default}%
            </div>
          </div>

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
                marginBottom: 10,
              }}
            >
              Risk Tier
            </div>

            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 24,
                fontWeight: 600,
                color: "#b33a3a",
              }}
            >
              {assessment.risk_tier}
            </div>
          </div>

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
                marginBottom: 10,
              }}
            >
              Model Confidence
            </div>

            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 32,
                fontWeight: 600,
                color: "var(--ink)",
              }}
            >
              {assessment.confidence}%
            </div>
          </div>
        </div>

        {/* Main explanation */}
        <div
          className="fade-up-2"
          style={{
            display: "grid",
            gridTemplateColumns: "1.4fr 0.6fr",
            gap: 20,
            alignItems: "start",
          }}
        >
          {/* Factor ledger */}
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
                Factor Contributions
              </h2>

              <p
                style={{
                  margin: "5px 0 0",
                  fontSize: 12,
                  color: "var(--muted)",
                }}
              >
                Factors influencing the generated assessment
              </p>
            </div>

            {assessment.factor_contributions.map((factor) => (
              <div
                key={factor.feature}
                style={{
                  padding: "20px 24px",
                  borderBottom: "1px solid var(--border)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    gap: 20,
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: "var(--ink)",
                        marginBottom: 6,
                      }}
                    >
                      {factor.feature}
                    </div>

                    <div
                      style={{
                        fontSize: 11,
                        color: "var(--muted)",
                        lineHeight: 1.5,
                      }}
                    >
                      Evidence: {factor.evidence}
                    </div>
                  </div>

                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "flex-end",
                      gap: 6,
                    }}
                  >
                    <span
                      style={{
                        ...getDirectionStyle(factor.direction),
                        padding: "5px 9px",
                        borderRadius: 20,
                        fontSize: 10,
                        fontWeight: 600,
                      }}
                    >
                      {factor.direction}
                    </span>

                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        color:
                          factor.contribution < 0
                            ? "#b33a3a"
                            : factor.contribution > 0
                              ? "#287a3d"
                              : "var(--muted)",
                      }}
                    >
                      {factor.contribution > 0 ? "+" : ""}
                      {factor.contribution} pts
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </section>

          {/* Right panel */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 20,
            }}
          >
            {/* Key reasons */}
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
                Primary factors associated with the assessment
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

            {/* Interpretation */}
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
                Assessment Interpretation
              </div>

              <div
                style={{
                  fontSize: 15,
                  fontWeight: 600,
                  marginBottom: 10,
                }}
              >
                Main assessment drivers
              </div>

              <p
                style={{
                  fontSize: 11,
                  lineHeight: 1.7,
                  opacity: 0.7,
                  margin: 0,
                }}
              >
                The assessment reflects the combined influence of the
                financial behaviour factors shown on this page. Each factor is
                presented with its observed evidence and contribution to the
                generated score.
              </p>
            </section>

            {/* Navigation */}
            <button
              className="btn-outline"
              onClick={() => go("fraudIntelligence")}
              style={{
                width: "100%",
                padding: "11px",
                fontSize: 12,
              }}
            >
              ← Fraud Intelligence
            </button>
          </div>
        </div>

        {/* Bottom navigation */}
        <div
          className="fade-up-3"
          style={{
            marginTop: 24,
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
            Explanation generated from the assessment feature outputs.
          </span>

          <button
            className="btn-outline"
            onClick={() => go("assessment")}
            style={{
              padding: "10px 16px",
              fontSize: 11,
            }}
          >
            ← Back to Assessment
          </button>
        </div>

        {lenderSession?.phone_number && (
          <div
            style={{
              marginTop: 40,
              fontSize: 11,
              color: "var(--muted)",
            }}
          >
            Lender session: {lenderSession.phone_number}
          </div>
        )}
      </main>
    </div>
  );
}
