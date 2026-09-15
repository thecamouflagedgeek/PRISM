import { Nav } from "../components/Nav";

export default function FraudIntelligencePage({ go, lenderSession }) {
  const fraudSummary = {
    application_id: "PR-1022",
    borrower_id: "BR-0037",
    fraud_flags: 0,
    overall_status: "No Flags Detected",
  };

  const checks = [
    {
      check: "Document Integrity",
      status: "Passed",
      severity: "None",
      evidence: "Document structure and extracted content are consistent.",
    },
    {
      check: "Cross-Document Consistency",
      status: "Passed",
      severity: "None",
      evidence: "Key borrower information is consistent across submitted documents.",
    },
    {
      check: "Transaction Anomaly Check",
      status: "Passed",
      severity: "None",
      evidence: "No significant transaction pattern anomalies identified.",
    },
    {
      check: "Income Consistency",
      status: "Passed",
      severity: "None",
      evidence: "Reported income is consistent with extracted financial records.",
    },
  ];

  const getStatusStyle = (status) => {
    if (status === "Passed") {
      return {
        background: "rgba(52, 168, 83, 0.10)",
        color: "#287a3d",
      };
    }

    if (status === "Review") {
      return {
        background: "rgba(255, 105, 55, 0.10)",
        color: "var(--orange)",
      };
    }

    return {
      background: "rgba(220, 53, 69, 0.10)",
      color: "#b42318",
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
        currentPage="fraudIntelligence"
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
          className="btn-outline"
          onClick={() => go("assessment")}
          style={{
            marginBottom: 28,
            padding: "9px 16px",
            fontSize: 13,
          }}
        >
          ← Back to Assessment
        </button>

        {/* Header */}
        <div style={{ marginBottom: 30 }}>
          <div
            style={{
              fontSize: 12,
              color: "var(--orange)",
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              marginBottom: 8,
            }}
          >
            Lender Workspace
          </div>

          <h1
            style={{
              fontSize: 32,
              fontWeight: 700,
              margin: 0,
              color: "var(--text)",
            }}
          >
            Fraud Intelligence
          </h1>

          <p
            style={{
              marginTop: 10,
              color: "var(--muted)",
              fontSize: 14,
              lineHeight: 1.6,
              maxWidth: 700,
            }}
          >
            Review fraud and anomaly checks associated with this borrower
            assessment.
          </p>
        </div>

        {/* Application information */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 16,
            marginBottom: 24,
          }}
        >
          <div className="card">
            <div className="label">Application ID</div>
            <div
              style={{
                fontSize: 20,
                fontWeight: 700,
                marginTop: 8,
              }}
            >
              {fraudSummary.application_id}
            </div>
          </div>

          <div className="card">
            <div className="label">Borrower ID</div>
            <div
              style={{
                fontSize: 20,
                fontWeight: 700,
                marginTop: 8,
              }}
            >
              {fraudSummary.borrower_id}
            </div>
          </div>

          <div className="card">
            <div className="label">Fraud Flags</div>
            <div
              style={{
                fontSize: 20,
                fontWeight: 700,
                marginTop: 8,
              }}
            >
              {fraudSummary.fraud_flags}
            </div>
          </div>
        </div>

        {/* Overall status */}
        <div
          className="card"
          style={{
            marginBottom: 24,
            padding: 24,
            borderLeft: "4px solid #34a853",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 20,
              flexWrap: "wrap",
            }}
          >
            <div>
              <div className="label">Fraud Assessment Status</div>

              <div
                style={{
                  fontSize: 24,
                  fontWeight: 700,
                  marginTop: 8,
                }}
              >
                {fraudSummary.overall_status}
              </div>

              <p
                style={{
                  color: "var(--muted)",
                  fontSize: 13,
                  margin: "8px 0 0",
                }}
              >
                No fraud or anomaly flags are currently associated with this
                assessment.
              </p>
            </div>

            <div
              style={{
                ...getStatusStyle("Passed"),
                padding: "10px 16px",
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 700,
              }}
            >
              0 Flags
            </div>
          </div>
        </div>

        {/* Checks */}
        <div
          className="card"
          style={{
            padding: 0,
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
                fontSize: 18,
              }}
            >
              Fraud & Anomaly Checks
            </h2>

            <p
              style={{
                margin: "6px 0 0",
                fontSize: 13,
                color: "var(--muted)",
              }}
            >
              Individual checks associated with the current assessment.
            </p>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: 13,
              }}
            >
              <thead>
                <tr>
                  <th className="table-head">Check</th>
                  <th className="table-head">Status</th>
                  <th className="table-head">Severity</th>
                  <th className="table-head">Evidence</th>
                </tr>
              </thead>

              <tbody>
                {checks.map((item) => (
                  <tr key={item.check}>
                    <td className="table-cell">
                      <strong>{item.check}</strong>
                    </td>

                    <td className="table-cell">
                      <span
                        style={{
                          ...getStatusStyle(item.status),
                          padding: "5px 10px",
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: 700,
                        }}
                      >
                        {item.status}
                      </span>
                    </td>

                    <td className="table-cell">
                      <span style={{ color: "var(--muted)" }}>
                        {item.severity}
                      </span>
                    </td>

                    <td
                      className="table-cell"
                      style={{
                        color: "var(--muted)",
                        maxWidth: 420,
                      }}
                    >
                      {item.evidence}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Prototype note */}
        <div
          style={{
            marginTop: 20,
            padding: "14px 18px",
            borderRadius: 8,
            background: "rgba(255, 105, 55, 0.06)",
            border: "1px solid rgba(255, 105, 55, 0.15)",
            color: "var(--muted)",
            fontSize: 12,
            lineHeight: 1.6,
          }}
        >
          <strong style={{ color: "var(--text)" }}>
            Prototype data:
          </strong>{" "}
          Fraud intelligence results shown here are placeholder assessment
          outputs pending integration with the backend fraud/anomaly engine.
        </div>

        {/* Navigation */}
        <div
          style={{
            display: "flex",
            gap: 12,
            marginTop: 30,
          }}
        >
          <button
            className="btn-outline"
            onClick={() => go("assessment")}
          >
            ← Assessment
          </button>

          <button
            className="btn-primary btn-orange"
            onClick={() => go("explainability")}
          >
            View Explainability →
          </button>
        </div>

        {/* Session */}
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