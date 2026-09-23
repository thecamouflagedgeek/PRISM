import { Nav } from "../components/Nav";

export default function DocumentReview({ go, lenderSession, result, lenderAssessment }) {
  const mockDocuments = [
    {
      type: "Bank Statement",
      file: "bank_statement.pdf",
      period: "Apr 2026 – Sep 2026",
      status: "Verified",
      extraction: "Complete",
      fields: 18,
      confidence: "94.2%",
    },
    {
      type: "Salary Slip",
      file: "salary_slip.pdf",
      period: "Aug 2026",
      status: "Verified",
      extraction: "Complete",
      fields: 9,
      confidence: "97.1%",
    },
    {
      type: "Utility Bill",
      file: "utility_bill.pdf",
      period: "Aug 2026",
      status: "Pending",
      extraction: "Review Required",
      fields: 7,
      confidence: "81.4%",
    },
  ];

  const mockExtractedFields = [
    {
      field: "Monthly Income",
      value: "₹58,400",
      source: "Salary Slip",
      status: "Verified",
    },
    {
      field: "Average Monthly Balance",
      value: "₹31,250",
      source: "Bank Statement",
      status: "Verified",
    },
    {
      field: "Total Credits",
      value: "₹72,800",
      source: "Bank Statement",
      status: "Verified",
    },
    {
      field: "Total Debits",
      value: "₹68,430",
      source: "Bank Statement",
      status: "Verified",
    },
    {
      field: "Utility Payment Status",
      value: "2 delayed payments",
      source: "Utility Bill",
      status: "Review",
    },
  ];

  const assessmentResult = lenderAssessment ?? result;
  const documentRisk = assessmentResult?.document_risk ?? {};
  const features = assessmentResult?.features ?? {};
  const reviewStatus = documentRisk.status === "CONSISTENT" ? "Verified" : "Review";
  const documents = Array.isArray(assessmentResult?.documents) ? assessmentResult.documents.map((document) => ({
    type: document.document_type?.replaceAll("_", " ") ?? "Document",
    file: document.file_name ?? "Submitted document",
    period: document.upload_timestamp ? new Date(document.upload_timestamp).toLocaleDateString("en-IN") : "Assessment session",
    status: document.processing_status === "OCR_COMPLETED" ? reviewStatus : document.processing_status ?? reviewStatus,
    extraction: document.processing_status === "OCR_COMPLETED" ? "Complete" : "Review Required",
    fields: 0,
    confidence: "Not reported",
  })) : assessmentResult ? Object.entries(features).filter(([, value]) => value).map(([source, values]) => ({
    type: source === "bank" ? "Bank Statement" : source === "salary" ? "Salary Slip" : "Utility Bill",
    file: "Submitted document", period: "Assessment session", status: reviewStatus,
    extraction: "Complete", fields: Object.keys(values ?? {}).length, confidence: "Not reported",
  })) : mockDocuments;
  const extractedFields = Array.isArray(features) ? features.map((feature) => ({
    field: feature.feature_name?.replaceAll("_", " ") ?? "Feature",
    value: feature.feature_value ?? "Not available",
    source: feature.feature_source ?? "Document",
    status: reviewStatus,
  })) : assessmentResult ? Object.entries(features).flatMap(([source, values]) => Object.entries(values ?? {}).slice(0, 8).map(([field, value]) => ({
    field: field.replaceAll("_", " "), value: value == null ? "Not available" : String(value),
    source: source === "bank" ? "Bank Statement" : source === "salary" ? "Salary Slip" : "Utility Bill", status: reviewStatus,
  }))) : mockExtractedFields;

  const getStatusStyle = (status) => {
    if (status === "Verified") {
      return {
        background: "rgba(52, 168, 83, 0.10)",
        color: "#287a3d",
      };
    }

    return {
      background: "rgba(255, 105, 55, 0.10)",
      color: "var(--orange)",
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
        currentPage="documentReview"
        onLogoClick={() => go("landing")}
      />

      <main
        style={{
          maxWidth: 1200,
          margin: "0 auto",
          padding: "50px 40px 80px",
        }}
      >
        {/* HEADER */}
        <div
          className="fade-up"
          style={{
            marginBottom: 32,
          }}
        >
          <button
            onClick={() => go("assessment")}
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
            ← Assessment
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
            Document Review
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-end",
              gap: 30,
            }}
          >
            <div>
              <h1
                className="display"
                style={{
                  fontSize: 42,
                  color: "var(--ink)",
                  margin: 0,
                }}
              >
                Financial Documents
              </h1>

              <p
                style={{
                  marginTop: 10,
                  color: "var(--muted)",
                  fontSize: 13,
                  lineHeight: 1.6,
                }}
              >
                Review document verification and extracted financial
                information for this assessment.
              </p>
            </div>

            <div
              style={{
                textAlign: "right",
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  color: "var(--muted)",
                  marginBottom: 4,
                }}
              >
                Application
              </div>

              <div
                style={{
                  fontFamily: "'Syne', sans-serif",
                  fontSize: 15,
                  fontWeight: 600,
                  color: "var(--ink)",
                }}
              >
                PR-1022
              </div>
            </div>
          </div>
        </div>

        {/* DOCUMENT SUMMARY */}
        <div
          className="fade-up-1"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 14,
            marginBottom: 22,
          }}
        >
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
              Documents Submitted
            </div>

            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 30,
                fontWeight: 600,
                color: "var(--ink)",
              }}
            >
              3
            </div>
          </div>

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
              Verified
            </div>

            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 30,
                fontWeight: 600,
                color: "#287a3d",
              }}
            >
              2
            </div>
          </div>

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
              Requires Review
            </div>

            <div
              style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: 30,
                fontWeight: 600,
                color: "var(--orange)",
              }}
            >
              1
            </div>
          </div>
        </div>

        {/* DOCUMENT LIST */}
        <section
          className="fade-up-2"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 14,
            overflow: "hidden",
            marginBottom: 22,
          }}
        >
          <div
            style={{
              padding: "21px 24px",
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
              Submitted Documents
            </h2>

            <p
              style={{
                margin: "5px 0 0",
                fontSize: 12,
                color: "var(--muted)",
              }}
            >
              Document processing and verification status
            </p>
          </div>

          {documents.map((document) => (
            <div
              key={document.file}
              style={{
                display: "grid",
                gridTemplateColumns:
                  "1.3fr 0.9fr 0.8fr 0.8fr 0.8fr 0.7fr",
                gap: 15,
                alignItems: "center",
                padding: "19px 24px",
                borderBottom: "1px solid var(--border)",
              }}
            >
              {/* Document */}
              <div>
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: "var(--ink)",
                  }}
                >
                  {document.type}
                </div>

                <div
                  style={{
                    fontSize: 10,
                    color: "var(--muted)",
                    marginTop: 4,
                  }}
                >
                  {document.file}
                </div>
              </div>

              {/* Period */}
              <div>
                <div
                  style={{
                    fontSize: 10,
                    color: "var(--muted)",
                    marginBottom: 4,
                  }}
                >
                  Period
                </div>

                <span
                  style={{
                    fontSize: 11,
                    color: "var(--ink2)",
                  }}
                >
                  {document.period}
                </span>
              </div>

              {/* Verification */}
              <div>
                <div
                  style={{
                    fontSize: 10,
                    color: "var(--muted)",
                    marginBottom: 5,
                  }}
                >
                  Verification
                </div>

                <span
                  style={{
                    ...getStatusStyle(document.status),
                    display: "inline-flex",
                    padding: "5px 9px",
                    borderRadius: 20,
                    fontSize: 10,
                    fontWeight: 600,
                  }}
                >
                  {document.status}
                </span>
              </div>

              {/* Extraction */}
              <div>
                <div
                  style={{
                    fontSize: 10,
                    color: "var(--muted)",
                    marginBottom: 4,
                  }}
                >
                  Extraction
                </div>

                <span
                  style={{
                    fontSize: 11,
                    color:
                      document.extraction === "Complete"
                        ? "#287a3d"
                        : "var(--orange)",
                    fontWeight: 500,
                  }}
                >
                  {document.extraction}
                </span>
              </div>

              {/* Confidence */}
              <div>
                <div
                  style={{
                    fontSize: 10,
                    color: "var(--muted)",
                    marginBottom: 4,
                  }}
                >
                  Confidence
                </div>

                <span
                  style={{
                    fontSize: 11,
                    color: "var(--ink2)",
                    fontWeight: 500,
                  }}
                >
                  {document.confidence}
                </span>
              </div>

              {/* Action */}
              <button
                onClick={() => {}}
                className="btn-outline"
                style={{
                  padding: "8px 10px",
                  fontSize: 10,
                }}
              >
                Inspect
              </button>
            </div>
          ))}
        </section>

        {/* EXTRACTED INFORMATION */}
        <section
          className="fade-up-3"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 14,
            overflow: "hidden",
            marginBottom: 22,
          }}
        >
          <div
            style={{
              padding: "21px 24px",
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
              Extracted Financial Information
            </h2>

            <p
              style={{
                margin: "5px 0 0",
                fontSize: 12,
                color: "var(--muted)",
              }}
            >
              Structured values derived from submitted documents
            </p>
          </div>

          {/* Header */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1.2fr 1fr 1fr 0.7fr",
              padding: "13px 24px",
              borderBottom: "1px solid var(--border)",
              fontSize: 10,
              color: "var(--muted)",
              textTransform: "uppercase",
              letterSpacing: "0.07em",
              fontWeight: 600,
            }}
          >
            <span>Field</span>
            <span>Extracted Value</span>
            <span>Source</span>
            <span>Status</span>
          </div>

          {extractedFields.map((item) => (
            <div
              key={item.field}
              style={{
                display: "grid",
                gridTemplateColumns: "1.2fr 1fr 1fr 0.7fr",
                padding: "16px 24px",
                borderBottom: "1px solid var(--border)",
                alignItems: "center",
                fontSize: 12,
              }}
            >
              <span
                style={{
                  color: "var(--ink2)",
                  fontWeight: 500,
                }}
              >
                {item.field}
              </span>

              <span
                style={{
                  color: "var(--ink)",
                  fontWeight: 600,
                }}
              >
                {item.value}
              </span>

              <span
                style={{
                  color: "var(--muted)",
                }}
              >
                {item.source}
              </span>

              <span
                style={{
                  color:
                    item.status === "Verified"
                      ? "#287a3d"
                      : "var(--orange)",
                  fontSize: 10,
                  fontWeight: 600,
                }}
              >
                {item.status}
              </span>
            </div>
          ))}
        </section>

        {/* PIPELINE NOTE */}
        <div
          className="fade-up-3"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 20,
            padding: "18px 20px",
            background: "rgba(255, 105, 55, 0.05)",
            border: "1px solid rgba(255, 105, 55, 0.15)",
            borderRadius: 12,
          }}
        >
          <div>
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "var(--ink)",
                marginBottom: 4,
              }}
            >
              Document Processing
            </div>

            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
                lineHeight: 1.5,
              }}
            >
              Documents are processed through extraction, OCR where
              required, structured information extraction and
              validation before entering the scoring pipeline.
            </div>
          </div>

          <button
            className="btn-outline"
            onClick={() => go("assessment")}
            style={{
              padding: "10px 15px",
              fontSize: 11,
              whiteSpace: "nowrap",
            }}
          >
            Back to Assessment →
          </button>
        </div>

        {/* LENDER */}
        <div
          style={{
            marginTop: 18,
            textAlign: "right",
            fontSize: 10,
            color: "var(--muted)",
          }}
        >
          Lender: {lenderSession?.phone_number || "Authenticated"}
        </div>
      </main>
    </div>
  );
}
