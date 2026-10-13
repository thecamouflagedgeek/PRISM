import { Nav } from "../components/Nav";

export default function FraudIntelligencePage({ go, lenderSession, result, lenderAssessment }) {
  const assessmentResult = lenderAssessment ?? result;
  const fraud = assessmentResult?.fraud_risk && typeof assessmentResult.fraud_risk === "object"
    ? assessmentResult.fraud_risk
    : {};
  const flags = Array.isArray(fraud.flags) ? fraud.flags.filter((flag) => flag && typeof flag === "object") : [];
  const EvidenceDisplay = ({ evidence, fallback }) => {
  if (evidence == null) {
    return <span>{fallback ?? "No evidence was provided."}</span>;
  }

  if (
    typeof evidence === "string" ||
    typeof evidence === "number" ||
    typeof evidence === "boolean"
  ) {
    return <span>{String(evidence)}</span>;
  }

  const nearZeroBalances = Array.isArray(evidence.near_zero_balances)
    ? evidence.near_zero_balances
    : [];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        minWidth: 0,
      }}
    >
      {/* Summary values */}
      {(evidence.near_zero_count !== undefined ||
        evidence.negative_balance_count !== undefined) && (
        <div
          style={{
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
          }}
        >
          {evidence.near_zero_count !== undefined && (
            <div
              style={{
                padding: "7px 10px",
                borderRadius: 7,
                background: "#f6f6f6",
                fontSize: 11,
              }}
            >
              <strong>Near-zero count:</strong>{" "}
              {evidence.near_zero_count}
            </div>
          )}

          {evidence.negative_balance_count !== undefined && (
            <div
              style={{
                padding: "7px 10px",
                borderRadius: 7,
                background: "#f6f6f6",
                fontSize: 11,
              }}
            >
              <strong>Negative balance count:</strong>{" "}
              {evidence.negative_balance_count}
            </div>
          )}
        </div>
      )}

      {/* Balance observations */}
      {nearZeroBalances.length > 0 && (
        <div>
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              marginBottom: 6,
            }}
          >
            Near-zero balance observations
          </div>

          <div
            style={{
              maxHeight: 150,
              overflowY: "auto",
              border: "1px solid #e5e5e5",
              borderRadius: 7,
            }}
          >
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: 11,
              }}
            >
              <thead>
                <tr>
                  <th
                    style={{
                      textAlign: "left",
                      padding: "7px 9px",
                      borderBottom: "1px solid #e5e5e5",
                    }}
                  >
                    Date
                  </th>

                  <th
                    style={{
                      textAlign: "right",
                      padding: "7px 9px",
                      borderBottom: "1px solid #e5e5e5",
                    }}
                  >
                    Balance
                  </th>
                </tr>
              </thead>

              <tbody>
                {nearZeroBalances.map((item, index) => (
                  <tr key={`${item.date}-${index}`}>
                    <td
                      style={{
                        padding: "6px 9px",
                        borderBottom: "1px solid #f0f0f0",
                      }}
                    >
                      {item.date || "—"}
                    </td>

                    <td
                      style={{
                        padding: "6px 9px",
                        textAlign: "right",
                        borderBottom: "1px solid #f0f0f0",
                      }}
                    >
                      {item.balance !== undefined
                        ? `₹${Number(item.balance).toFixed(2)}`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Any other evidence fields */}
      {Object.entries(evidence)
        .filter(
          ([key]) =>
            key !== "near_zero_count" &&
            key !== "negative_balance_count" &&
            key !== "near_zero_balances" &&
            key !== "negative_balances"
        )
        .map(([key, value]) => (
          <div
            key={key}
            style={{
              fontSize: 11,
              lineHeight: 1.5,
            }}
          >
            <strong>
              {key.replace(/_/g, " ")}:
            </strong>{" "}
            {typeof value === "object"
              ? JSON.stringify(value)
              : String(value)}
          </div>
        ))}
    </div>
  );
};
  const fraudSummary = {
    application_id: assessmentResult?.application_id ?? lenderSession?.application_id ?? "Current session",
    borrower_id: assessmentResult?.application?.borrower_phone ?? lenderSession?.phone_number ?? "Borrower",
    fraud_flags: fraud.rule_count ?? flags.length,
    overall_status: fraud.fraud_status ?? "Unavailable",
  };
 const checks = flags.map((flag, index) => ({
  id: `${flag.rule ?? "fraud-rule"}-${index}`,
  check: flag.rule ?? "Fraud rule",
  status: flag.severity === "HIGH" ? "Review" : "Passed",
  severity: flag.severity ?? flag.category ?? "Unspecified",
  evidence: flag.evidence,
  message: flag.message,
}));
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
                {flags.length ? "Backend fraud rules identified the checks below." : "No fraud or anomaly flags are currently associated with this assessment."}
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
              {fraudSummary.fraud_flags} Flags
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
  {checks.length ? (
    checks.map((item) => (
      <tr key={item.id}>
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
            verticalAlign: "top",
          }}
        >
          <EvidenceDisplay
            evidence={item.evidence}
            fallback={item.message}
          />
        </td>
      </tr>
    ))
  ) : (
    <tr>
      <td className="table-cell" colSpan="4">
        No fraud flags reported by the assessment.
      </td>
    </tr>
  )}
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
            Assessment metadata:
          </strong>{" "}
          Engine {fraud.engine_version ?? "not reported"} · {fraud.score_semantics ?? "Fraud score is independent of credit risk."}
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
