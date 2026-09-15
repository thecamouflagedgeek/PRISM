import { Nav } from "../components/Nav";

export default function AuditLogPage({ go, lenderSession }) {
  const auditLogs = [
    {
      audit_id: "AUD-00871",
      application_id: "PR-1022",
      action: "Assessment Viewed",
      entity: "Risk Score",
      performed_by: "Lender",
      timestamp: "16 Sep 2026, 10:42 AM",
      status: "Success",
    },
    {
      audit_id: "AUD-00870",
      application_id: "PR-1022",
      action: "Document Review",
      entity: "Documents",
      performed_by: "Lender",
      timestamp: "16 Sep 2026, 10:38 AM",
      status: "Success",
    },
    {
      audit_id: "AUD-00869",
      application_id: "PR-1023",
      action: "Assessment Viewed",
      entity: "Risk Score",
      performed_by: "Lender",
      timestamp: "16 Sep 2026, 10:21 AM",
      status: "Success",
    },
    {
      audit_id: "AUD-00868",
      application_id: "PR-1021",
      action: "Application Reviewed",
      entity: "Application",
      performed_by: "Lender",
      timestamp: "16 Sep 2026, 09:57 AM",
      status: "Success",
    },
    {
      audit_id: "AUD-00867",
      application_id: "PR-1022",
      action: "Fraud Intelligence Viewed",
      entity: "Fraud Check",
      performed_by: "Lender",
      timestamp: "16 Sep 2026, 09:44 AM",
      status: "Success",
    },
    {
      audit_id: "AUD-00866",
      application_id: "PR-1024",
      action: "Assessment Viewed",
      entity: "Risk Score",
      performed_by: "Lender",
      timestamp: "16 Sep 2026, 09:32 AM",
      status: "Success",
    },
    {
      audit_id: "AUD-00865",
      application_id: "PR-1023",
      action: "Document Review",
      entity: "Documents",
      performed_by: "Lender",
      timestamp: "16 Sep 2026, 09:18 AM",
      status: "Success",
    },
    {
      audit_id: "AUD-00864",
      application_id: "PR-1020",
      action: "Application Reviewed",
      entity: "Application",
      performed_by: "Lender",
      timestamp: "16 Sep 2026, 08:56 AM",
      status: "Success",
    },
  ];

  const successCount = auditLogs.filter(
    (log) => log.status === "Success"
  ).length;

  const pendingCount = auditLogs.filter(
    (log) => log.status === "Pending"
  ).length;

  return (
    <div
      className="dot-grid"
      style={{
        minHeight: "100vh",
        backgroundColor: "var(--bg)",
      }}
    >
      <Nav
        currentPage="auditLog"
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
          onClick={() => go("lenderDashboard")}
          style={{
            background: "none",
            border: "none",
            padding: 0,
            color: "var(--muted)",
            fontSize: 12,
            cursor: "pointer",
            marginBottom: 24,
          }}
        >
          ← Back to Dashboard
        </button>

        {/* Header */}
        <div style={{ marginBottom: 34 }}>
          <div
            style={{
              fontSize: 11,
              color: "var(--orange)",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              marginBottom: 10,
              fontWeight: 600,
            }}
          >
            System Traceability
          </div>

          <h1
            style={{
              fontFamily: "'Syne', sans-serif",
              fontSize: 38,
              fontWeight: 600,
              margin: 0,
              letterSpacing: "-0.03em",
            }}
          >
            Audit Log
          </h1>

          <p
            style={{
              marginTop: 10,
              color: "var(--muted)",
              fontSize: 14,
            }}
          >
            Track application activity and system actions across the lender
            workflow.
          </p>
        </div>

        {/* Summary Cards */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 16,
            marginBottom: 28,
          }}
        >
          {/* Total Events */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: 22,
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
              Total Events
            </div>

            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 32,
                fontWeight: 600,
              }}
            >
              42
            </div>

            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                marginTop: 6,
              }}
            >
              Recorded activities
            </div>
          </div>

          {/* Successful */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: 22,
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
              Successful
            </div>

            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 32,
                fontWeight: 600,
                color: "#287a3d",
              }}
            >
              38
            </div>

            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                marginTop: 6,
              }}
            >
              Completed actions
            </div>
          </div>

          {/* Pending */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: 22,
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
              Pending
            </div>

            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 32,
                fontWeight: 600,
              }}
            >
              4
            </div>

            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                marginTop: 6,
              }}
            >
              Awaiting completion
            </div>
          </div>
        </div>

        {/* Filters */}
        <div
          style={{
            display: "flex",
            gap: 12,
            marginBottom: 18,
            alignItems: "center",
          }}
        >
          <input
            type="text"
            placeholder="Search application or action..."
            style={{
              flex: 1,
              maxWidth: 420,
              padding: "11px 14px",
              borderRadius: 9,
              border: "1px solid var(--border)",
              background: "var(--surface)",
              color: "var(--text)",
              fontSize: 12,
              outline: "none",
            }}
          />

          <button
            className="btn-outline"
            style={{
              padding: "10px 16px",
              fontSize: 12,
            }}
          >
            All Events ▾
          </button>
        </div>

        {/* Audit Table */}
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 14,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "20px 22px",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 16,
                fontWeight: 600,
              }}
            >
              Activity History
            </div>

            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                marginTop: 5,
              }}
            >
              Recorded actions within the PRISM lender workflow
            </div>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                minWidth: 900,
              }}
            >
              <thead>
                <tr
                  style={{
                    borderBottom: "1px solid var(--border)",
                  }}
                >
                  {[
                    "Timestamp",
                    "Application",
                    "Action",
                    "Entity",
                    "Performed By",
                    "Status",
                  ].map((heading) => (
                    <th
                      key={heading}
                      style={{
                        padding: "13px 18px",
                        textAlign: "left",
                        fontSize: 10,
                        color: "var(--muted)",
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        fontWeight: 500,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody>
                {auditLogs.map((log) => (
                  <tr
                    key={log.audit_id}
                    style={{
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <td
                      style={{
                        padding: "16px 18px",
                        fontSize: 11,
                        color: "var(--muted)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {log.timestamp}
                    </td>

                    <td
                      style={{
                        padding: "16px 18px",
                        fontSize: 12,
                        fontWeight: 600,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {log.application_id}
                    </td>

                    <td
                      style={{
                        padding: "16px 18px",
                        fontSize: 12,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {log.action}
                    </td>

                    <td
                      style={{
                        padding: "16px 18px",
                        fontSize: 12,
                        color: "var(--muted)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {log.entity}
                    </td>

                    <td
                      style={{
                        padding: "16px 18px",
                        fontSize: 12,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {log.performed_by}
                    </td>

                    <td
                      style={{
                        padding: "16px 18px",
                        whiteSpace: "nowrap",
                      }}
                    >
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "5px 9px",
                          borderRadius: 999,
                          fontSize: 10,
                          fontWeight: 600,
                          background:
                            log.status === "Success"
                              ? "rgba(52, 168, 83, 0.10)"
                              : "rgba(255, 105, 55, 0.10)",
                          color:
                            log.status === "Success"
                              ? "#287a3d"
                              : "var(--orange)",
                        }}
                      >
                        {log.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Table Footer */}
          <div
            style={{
              padding: "15px 20px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: 11,
              color: "var(--muted)",
            }}
          >
            <span>Showing recent audit events</span>
            <span>Prototype data</span>
          </div>
        </div>

        {/* Traceability Note */}
        <div
          style={{
            marginTop: 20,
            padding: "16px 18px",
            borderRadius: 12,
            border: "1px solid var(--border)",
            background: "rgba(255, 255, 255, 0.02)",
          }}
        >
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              marginBottom: 6,
            }}
          >
            Auditability
          </div>

          <div
            style={{
              fontSize: 11,
              color: "var(--muted)",
              lineHeight: 1.6,
            }}
          >
            PRISM records application-level actions to support traceability
            across document review, risk assessment, fraud checks and
            explainability workflows. The displayed entries are prototype
            audit records and will be connected to the backend audit-log
            store during integration.
          </div>
        </div>

        {/* Navigation */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: 30,
          }}
        >
          <button
            className="btn-outline"
            onClick={() => go("applications")}
            style={{
              padding: "11px 18px",
              fontSize: 12,
            }}
          >
            ← Applications
          </button>

          <button
            className="btn-primary btn-orange"
            onClick={() => go("lenderDashboard")}
            style={{
              padding: "11px 18px",
              fontSize: 12,
            }}
          >
            Back to Dashboard
          </button>
        </div>

        {/* Session */}
        {lenderSession?.phone_number && (
          <div
            style={{
              marginTop: 28,
              textAlign: "right",
              fontSize: 10,
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