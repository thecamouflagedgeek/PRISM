import { useEffect, useState } from "react";
import { Nav } from "../components/Nav";
import { api } from "../services/api";

export default function ApplicationsPage({ go, lenderSession, setLenderAssessment }) {
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeFilter, setActiveFilter] = useState("All");
  const [search, setSearch] = useState("");

  useEffect(() => {
    let active = true;
    api.lenderApplications()
      .then(({ applications: rows }) => {
        if (!active) return;
        setApplications(rows.map((item) => ({
          id: item.application_id,
          borrower: item.borrower_phone ?? "Not available",
          score: item.risk_score ?? "—",
          pd: item.probability_of_default == null ? "—" : `${(Number(item.probability_of_default) * 100).toFixed(1)}%`,
          risk: item.risk_tier ?? "Not assessed",
          status: item.application_status ?? "IN_PROGRESS",
          documents: String(item.document_count ?? 0),
          date: item.application_date ? new Date(item.application_date).toLocaleDateString("en-IN") : "—",
        })));
      })
      .catch((requestError) => active && setError(requestError.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const openAssessment = async (applicationId) => {
    setError("");
    try {
      const assessment = await api.lenderApplication(applicationId);
      setLenderAssessment(assessment);
      go("assessment");
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  const filteredApplications = applications.filter((application) => {
  if (activeFilter === "All") {
    return true;
  }

  if (activeFilter === "New") {
    return String(application.status || "").toUpperCase() === "NEW";
  }

  if (activeFilter === "Under Review") {
    return String(application.status || "").toUpperCase() === "IN_PROGRESS";
  }

  if (activeFilter === "Reviewed") {
    return String(application.status || "").toUpperCase() === "ASSESSED";
  }

  return true;
});
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
      {/* NAV */}
      <Nav
        currentPage="applications"
        onLogoClick={() => go("landing")}
      />

      <main
        style={{
          maxWidth: 1200,
          margin: "0 auto",
          padding: "52px 40px 80px",
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
            marginBottom: 36,
            gap: 30,
          }}
        >
          <div>
            <button
              onClick={() => go("lenderDashboard")}
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
              ← Dashboard
            </button>

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
              Lender Workspace
            </div>

            <h1
              className="display"
              style={{
                fontSize: 44,
                color: "var(--ink)",
                margin: 0,
              }}
            >
              Applications
            </h1>

            <p
              style={{
                marginTop: 12,
                color: "var(--muted)",
                fontSize: 14,
                lineHeight: 1.6,
                fontWeight: 300,
              }}
            >
              Review borrower submissions and access their
              risk assessments.
            </p>
          </div>

          <div
            style={{
              fontSize: 12,
              color: "var(--muted)",
              paddingBottom: 5,
            }}
          >
            {loading ? "Loading applications…" : `${applications.length} applications`}
          </div>
        </div>

        {/* ------------------------------------------- */}
        {/* FILTER / SEARCH BAR */}
        {/* ------------------------------------------- */}
        <div
          className="fade-up-1"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 16,
            marginBottom: 18,
          }}
        >
          <div
            style={{
              display: "flex",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            {["All", "New", "Under Review", "Reviewed"].map((filter) => (
            <button
              key={filter}
              onClick={() => setActiveFilter(filter)}
              className={
                activeFilter === filter
                  ? "btn-primary btn-orange"
                  : "btn-outline"
              }
              style={{
                padding: "9px 15px",
                fontSize: 11,
              }}
            >
              {filter}
            </button>
          ))}
          </div>

          <input
            className="input-field"
            placeholder="Search application or borrower..."
            value={search}
            onChange={(event) => setSearch(event.target.value)} 
            style={{
              width: 270,
              padding: "10px 13px",
              fontSize: 12,
            }}
          />
        </div>

        {/* ------------------------------------------- */}
        {/* APPLICATION TABLE */}
        {/* ------------------------------------------- */}
        <section
          className="fade-up-2"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 14,
            overflow: "hidden",
          }}
        >
          {/* Table header */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "1.05fr 0.9fr 0.65fr 0.8fr 0.8fr 0.85fr 0.75fr 0.55fr",
              padding: "14px 22px",
              borderBottom: "1px solid var(--border)",
              fontSize: 10,
              color: "var(--muted)",
              textTransform: "uppercase",
              letterSpacing: "0.07em",
              fontWeight: 600,
              alignItems: "center",
            }}
          >
            <span>Application</span>
            <span>Borrower</span>
            <span>Score</span>
            <span>PD</span>
            <span>Risk</span>
            <span>Status</span>
            <span>Documents</span>
            <span></span>
          </div>

          {/* Rows */}
          {error && <div style={{ padding: "18px 22px", color: "#b33a3a", fontSize: 12 }}>{error}</div>}
          {!loading && !error && filteredApplications.length === 0 && (
  <div
    style={{
      padding: "18px 22px",
      color: "var(--muted)",
      fontSize: 12,
    }}
  >
    No applications match this filter.
  </div>
)}
{filteredApplications.map((application) => (
            <div
              key={application.id}
              style={{
                display: "grid",
                gridTemplateColumns:
                  "1.05fr 0.9fr 0.65fr 0.8fr 0.8fr 0.85fr 0.75fr 0.55fr",
                padding: "18px 22px",
                borderBottom: "1px solid var(--border)",
                alignItems: "center",
                fontSize: 12,
              }}
            >
              {/* Application */}
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

              {/* Borrower */}
              <span
                style={{
                  color: "var(--ink2)",
                  fontWeight: 500,
                }}
              >
                {application.borrower}
              </span>

              {/* Score */}
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

              {/* PD */}
              <span
                style={{
                  color: "var(--ink2)",
                }}
              >
                {application.pd}
              </span>

              {/* Risk */}
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

              {/* Status */}
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

              {/* Documents */}
              <span
                style={{
                  color:
                    application.documents === "3 / 3"
                      ? "var(--ink2)"
                      : "var(--orange)",
                  fontWeight: 500,
                }}
              >
                {application.documents}
              </span>

              {/* Action */}
              <button
                onClick={() => openAssessment(application.id)}
                style={{
                  border: "none",
                  background: "transparent",
                  color: "var(--orange)",
                  cursor: "pointer",
                  fontSize: 11,
                  fontWeight: 600,
                  padding: 0,
                  textAlign: "right",
                }}
              >
                Review →
              </button>
            </div>
          ))}
        </section>

        {/* ------------------------------------------- */}
        {/* FOOTNOTE */}
        {/* ------------------------------------------- */}
        <div
          className="fade-up-3"
          style={{
            marginTop: 18,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            fontSize: 11,
            color: "var(--muted)",
          }}
        >
          <span>
            Risk scores and PD values are generated by the PRISM
            assessment pipeline.
          </span>

          <span>
            Lender:{" "}
            {lenderSession?.phone_number || "Authenticated"}
          </span>
        </div>
      </main>
    </div>
  );
}
