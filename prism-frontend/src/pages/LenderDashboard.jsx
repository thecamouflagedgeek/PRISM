import { Nav } from "../components/Nav";

export default function LenderDashboard({ go, lenderSession }) {
  // --------------------------------------------------
  // MOCK DATA
  // Replace with backend API data later
  // --------------------------------------------------
  const applications = [
    {
      id: "PR-1024",
      borrower: "BR-0042",
      score: 742,
      risk: "Low Risk",
      status: "New",
      date: "16 Sep 2026",
    },
    {
      id: "PR-1023",
      borrower: "BR-0039",
      score: 581,
      risk: "Medium Risk",
      status: "Under Review",
      date: "16 Sep 2026",
    },
    {
      id: "PR-1022",
      borrower: "BR-0037",
      score: 364,
      risk: "High Risk",
      status: "New",
      date: "15 Sep 2026",
    },
    {
      id: "PR-1021",
      borrower: "BR-0034",
      score: 691,
      risk: "Medium Risk",
      status: "Reviewed",
      date: "15 Sep 2026",
    },
    {
      id: "PR-1020",
      borrower: "BR-0031",
      score: 817,
      risk: "Low Risk",
      status: "Reviewed",
      date: "14 Sep 2026",
    },
  ];

  // --------------------------------------------------
  // Helpers
  // --------------------------------------------------
  const getRiskStyle = (risk) => {
    if (risk === "Low Risk") {
      return {
        background: "rgba(52, 168, 83, 0.10)",
        color: "#287a3d",
      };
    }

    if (risk === "Medium Risk") {
      return {
        background: "rgba(245, 166, 35, 0.12)",
        color: "#a96c00",
      };
    }

    return {
      background: "rgba(220, 70, 70, 0.10)",
      color: "#b33a3a",
    };
  };

  const getStatusStyle = (status) => {
    if (status === "New") {
      return {
        background: "rgba(255, 105, 55, 0.10)",
        color: "var(--orange)",
      };
    }

    if (status === "Under Review") {
      return {
        background: "rgba(245, 166, 35, 0.10)",
        color: "#9a6800",
      };
    }

    return {
      background: "rgba(100, 100, 100, 0.08)",
      color: "var(--muted)",
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
      {/* NAVIGATION */}
      {/* --------------------------------------------- */}
      <Nav
        currentPage="lenderDashboard"
        onLogoClick={() => go("landing")}
      />

      {/* --------------------------------------------- */}
      {/* MAIN CONTENT */}
      {/* --------------------------------------------- */}
      <main
        style={{
          maxWidth: 1200,
          margin: "0 auto",
          padding: "58px 40px 80px",
        }}
      >
        {/* ------------------------------------------- */}
        {/* HEADER */}
        {/* ------------------------------------------- */}
        <div
          className="fade-up"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-end",
            gap: 30,
            marginBottom: 42,
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
                marginBottom: 12,
                fontFamily: "'Syne', sans-serif",
              }}
            >
              Lender Portal
            </div>

            <h1
              className="display"
              style={{
                fontSize: 48,
                color: "var(--ink)",
                margin: 0,
                lineHeight: 1.05,
              }}
            >
              Overview
            </h1>

            <p
              style={{
                marginTop: 14,
                color: "var(--muted)",
                fontSize: 15,
                lineHeight: 1.6,
                fontWeight: 300,
              }}
            >
              Monitor borrower applications, risk assessments and
              decision-ready insights.
            </p>
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              paddingBottom: 4,
            }}
          >
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: "50%",
                background: "var(--ink)",
                color: "white",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              L
            </div>

            <div>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: "var(--ink)",
                }}
              >
                Lender
              </div>

              <div
                style={{
                  fontSize: 11,
                  color: "var(--muted)",
                  marginTop: 2,
                }}
              >
                {lenderSession?.phone_number || "Authenticated"}
              </div>
            </div>
          </div>
        </div>

        {/* ------------------------------------------- */}
        {/* STAT CARDS */}
        {/* ------------------------------------------- */}
        <div
          className="fade-up-1"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 16,
            marginBottom: 42,
          }}
        >
          {/* Applications */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: "24px 22px",
            }}
          >
            <div
              style={{
                fontSize: 12,
                color: "var(--muted)",
                marginBottom: 14,
              }}
            >
              Total Applications
            </div>

            <div
              style={{
                fontSize: 34,
                fontWeight: 600,
                color: "var(--ink)",
                fontFamily: "'Syne', sans-serif",
              }}
            >
              24
            </div>

            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                marginTop: 8,
              }}
            >
              All borrower submissions
            </div>
          </div>

          {/* Pending */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: "24px 22px",
            }}
          >
            <div
              style={{
                fontSize: 12,
                color: "var(--muted)",
                marginBottom: 14,
              }}
            >
              Pending Review
            </div>

            <div
              style={{
                fontSize: 34,
                fontWeight: 600,
                color: "var(--ink)",
                fontFamily: "'Syne', sans-serif",
              }}
            >
              8
            </div>

            <div
              style={{
                fontSize: 11,
                color: "var(--orange)",
                marginTop: 8,
              }}
            >
              Requires attention
            </div>
          </div>

          {/* High Risk */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: "24px 22px",
            }}
          >
            <div
              style={{
                fontSize: 12,
                color: "var(--muted)",
                marginBottom: 14,
              }}
            >
              High Risk
            </div>

            <div
              style={{
                fontSize: 34,
                fontWeight: 600,
                color: "var(--ink)",
                fontFamily: "'Syne', sans-serif",
              }}
            >
              5
            </div>

            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                marginTop: 8,
              }}
            >
              Across active applications
            </div>
          </div>

          {/* Reviewed */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: "24px 22px",
            }}
          >
            <div
              style={{
                fontSize: 12,
                color: "var(--muted)",
                marginBottom: 14,
              }}
            >
              Reviewed
            </div>

            <div
              style={{
                fontSize: 34,
                fontWeight: 600,
                color: "var(--ink)",
                fontFamily: "'Syne', sans-serif",
              }}
            >
              11
            </div>

            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                marginTop: 8,
              }}
            >
              Completed assessments
            </div>
          </div>
        </div>

        {/* ------------------------------------------- */}
        {/* TWO COLUMN SECTION */}
        {/* ------------------------------------------- */}
        <div
          className="fade-up-2"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 330px",
            gap: 20,
            alignItems: "start",
          }}
        >
          {/* ----------------------------------------- */}
          {/* RECENT APPLICATIONS */}
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
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div>
                <h2
                  style={{
                    margin: 0,
                    fontSize: 17,
                    color: "var(--ink)",
                    fontFamily: "'Syne', sans-serif",
                  }}
                >
                  Recent Applications
                </h2>

                <p
                  style={{
                    margin: "5px 0 0",
                    fontSize: 12,
                    color: "var(--muted)",
                  }}
                >
                  Latest borrower assessments
                </p>
              </div>

              <button
                className="btn-outline"
                onClick={() => go("applications")}
                style={{
                  padding: "9px 15px",
                  fontSize: 12,
                }}
              >
                View all →
              </button>
            </div>

            {/* Table header */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1.1fr 1fr 0.7fr 1fr 1fr 0.6fr",
                padding: "13px 24px",
                borderBottom: "1px solid var(--border)",
                fontSize: 10,
                color: "var(--muted)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                fontWeight: 600,
              }}
            >
              <span>Application</span>
              <span>Borrower</span>
              <span>Score</span>
              <span>Risk</span>
              <span>Status</span>
              <span></span>
            </div>

            {/* Application rows */}
            {applications.map((application) => (
              <div
                key={application.id}
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "1.1fr 1fr 0.7fr 1fr 1fr 0.6fr",
                  padding: "18px 24px",
                  borderBottom: "1px solid var(--border)",
                  alignItems: "center",
                  fontSize: 12,
                  transition: "background 0.2s ease",
                }}
              >
                <div>
                  <div
                    style={{
                      fontWeight: 600,
                      color: "var(--ink)",
                    }}
                  >
                    {application.id}
                  </div>

                  <div
                    style={{
                      fontSize: 10,
                      color: "var(--muted)",
                      marginTop: 3,
                    }}
                  >
                    {application.date}
                  </div>
                </div>

                <span
                  style={{
                    color: "var(--ink2)",
                    fontWeight: 500,
                  }}
                >
                  {application.borrower}
                </span>

                <span
                  style={{
                    fontFamily: "'Syne', sans-serif",
                    fontWeight: 600,
                    fontSize: 14,
                    color: "var(--ink)",
                  }}
                >
                  {application.score}
                </span>

                <span
                  style={{
                    ...getRiskStyle(application.risk),
                    display: "inline-flex",
                    width: "fit-content",
                    padding: "5px 9px",
                    borderRadius: 20,
                    fontSize: 10,
                    fontWeight: 600,
                  }}
                >
                  {application.risk}
                </span>

                <span
                  style={{
                    ...getStatusStyle(application.status),
                    display: "inline-flex",
                    width: "fit-content",
                    padding: "5px 9px",
                    borderRadius: 20,
                    fontSize: 10,
                    fontWeight: 600,
                  }}
                >
                  {application.status}
                </span>

                <button
                  onClick={() => go("assessment")}
                  style={{
                    border: "none",
                    background: "transparent",
                    color: "var(--orange)",
                    cursor: "pointer",
                    fontSize: 12,
                    fontWeight: 600,
                    padding: 0,
                    textAlign: "right",
                  }}
                >
                  View →
                </button>
              </div>
            ))}
          </section>

          {/* ----------------------------------------- */}
          {/* RISK DISTRIBUTION */}
          {/* ----------------------------------------- */}
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
              Risk Distribution
            </h2>

            <p
              style={{
                margin: "5px 0 28px",
                fontSize: 12,
                color: "var(--muted)",
              }}
            >
              Active application portfolio
            </p>

            {/* Low */}
            <div style={{ marginBottom: 24 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: 9,
                }}
              >
                <span
                  style={{
                    fontSize: 12,
                    color: "var(--ink2)",
                  }}
                >
                  Low Risk
                </span>

                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: "var(--ink)",
                  }}
                >
                  11
                </span>
              </div>

              <div
                style={{
                  height: 7,
                  background: "var(--border)",
                  borderRadius: 10,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: "46%",
                    height: "100%",
                    background: "#287a3d",
                    borderRadius: 10,
                  }}
                />
              </div>
            </div>

            {/* Medium */}
            <div style={{ marginBottom: 24 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: 9,
                }}
              >
                <span
                  style={{
                    fontSize: 12,
                    color: "var(--ink2)",
                  }}
                >
                  Medium Risk
                </span>

                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: "var(--ink)",
                  }}
                >
                  8
                </span>
              </div>

              <div
                style={{
                  height: 7,
                  background: "var(--border)",
                  borderRadius: 10,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: "33%",
                    height: "100%",
                    background: "#a96c00",
                    borderRadius: 10,
                  }}
                />
              </div>
            </div>

            {/* High */}
            <div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: 9,
                }}
              >
                <span
                  style={{
                    fontSize: 12,
                    color: "var(--ink2)",
                  }}
                >
                  High Risk
                </span>

                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: "var(--ink)",
                  }}
                >
                  5
                </span>
              </div>

              <div
                style={{
                  height: 7,
                  background: "var(--border)",
                  borderRadius: 10,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: "21%",
                    height: "100%",
                    background: "#b33a3a",
                    borderRadius: 10,
                  }}
                />
              </div>
            </div>

            {/* Divider */}
            <div
              style={{
                height: 1,
                background: "var(--border)",
                margin: "30px 0 22px",
              }}
            />

            {/* Quick actions */}
            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                fontWeight: 600,
                marginBottom: 13,
              }}
            >
              Quick Access
            </div>

            <button
              className="btn-outline"
              onClick={() => go("applications")}
              style={{
                width: "100%",
                padding: "11px 14px",
                fontSize: 12,
                textAlign: "left",
                marginBottom: 9,
              }}
            >
              Applications →
            </button>

            <button
              className="btn-outline"
              onClick={() => go("auditLog")}
              style={{
                width: "100%",
                padding: "11px 14px",
                fontSize: 12,
                textAlign: "left",
              }}
            >
              Audit Log →
            </button>
          </section>
        </div>
      </main>
    </div>
  );
}