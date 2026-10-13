"""Opt-in persistent borrower-to-lender demo API; separate from production /assess."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Literal
import uuid

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/phase4/demo", tags=["Phase 4 Controlled Demo"])
PHASE2 = Path(__file__).resolve().parents[1] / "phase2"
SCORECARD = PHASE2 / "outputs" / "phase2f" / "frozen_shadow_scorecard.json"
SCORECARD_MANIFEST = Path(__file__).resolve().parent / "outputs" / "frozen_scorecard_manifest.json"
MAX_EVIDENCE_BYTES = 512 * 1024
REQUIRED_SCOPES = {"CREDIT_CARD_STATEMENTS", "BUREAU_REPAYMENT_HISTORY"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApplicationCreate(StrictModel):
    application_id: str = Field(min_length=4, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    borrower_reference: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    requested_loan_amount: float = Field(gt=0, le=100_000_000)
    loan_purpose: str = Field(min_length=2, max_length=100)
    employment_category: Literal["SALARIED", "SELF_EMPLOYED", "CONTRACT", "OTHER"]
    declared_monthly_income: float = Field(ge=0, le=100_000_000)
    contact_reference: str | None = Field(default=None, max_length=80)


class ConsentUpdate(StrictModel):
    grant: bool
    scopes: list[str] = Field(default_factory=list, max_length=10)


class CreditEvidenceUpload(StrictModel):
    evidence_type: Literal["CREDIT_ACCOUNT_REPAYMENT", "BANK_STATEMENT", "OTHER"]
    borrower_reference: str = Field(min_length=1, max_length=100)
    prediction_cutoff_month: str = Field(min_length=7, max_length=10)
    statements: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    repayment_history: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    borrower_account_count: int = Field(default=1, ge=1, le=100)


def _db_path() -> Path:
    configured = os.getenv("PHASE4_DEMO_DB_PATH")
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parent / "data" / "phase4_demo.sqlite3"


def _conn() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS applications (
        application_id TEXT PRIMARY KEY, borrower_reference TEXT NOT NULL,
        requested_loan_amount REAL NOT NULL, loan_purpose TEXT NOT NULL,
        employment_category TEXT NOT NULL, declared_monthly_income REAL NOT NULL,
        contact_reference TEXT, created_at TEXT NOT NULL, synthetic_demo INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS consents (
        application_id TEXT PRIMARY KEY REFERENCES applications(application_id) ON DELETE CASCADE,
        state TEXT NOT NULL, scopes_json TEXT NOT NULL, granted_at TEXT,
        withdrawn_at TEXT, updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS evidence (
        evidence_id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
        evidence_type TEXT NOT NULL, filename TEXT NOT NULL, sha256 TEXT NOT NULL,
        payload_json TEXT NOT NULL, submitted_at TEXT NOT NULL, synthetic_demo INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS assessments (
        assessment_id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
        evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id), status TEXT NOT NULL,
        model_identity TEXT, result_json TEXT NOT NULL, assessed_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_applications_borrower ON applications(borrower_reference);
      CREATE INDEX IF NOT EXISTS idx_assessments_application ON assessments(application_id, assessed_at);
    """)
    evidence_columns = {row["name"] for row in conn.execute("PRAGMA table_info(evidence)")}
    if "synthetic_demo" not in evidence_columns:
        conn.execute("ALTER TABLE evidence ADD COLUMN synthetic_demo INTEGER NOT NULL DEFAULT 0")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(row):
    return dict(row) if row is not None else None


def _authorize(authorization: str | None = Header(default=None)):
    if os.getenv("ENABLE_PHASE4_DEMO", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=404, detail={"code": "PHASE4_DEMO_DISABLED"})
    expected = os.getenv("PHASE4_DEMO_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail={"code": "PHASE4_DEMO_TOKEN_NOT_CONFIGURED"})
    supplied = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else ""
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail={"code": "PHASE4_DEMO_UNAUTHORIZED"})


def _application(conn, application_id):
    row = conn.execute("SELECT * FROM applications WHERE application_id=?", (application_id,)).fetchone()
    if row is None:
        raise HTTPException(404, detail={"code": "APPLICATION_NOT_FOUND"})
    return row


def _safe_name(name: str | None) -> str:
    base = Path(name or "evidence.json").name
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", base)[:100]
    return cleaned or "evidence.json"


def _is_packaged_synthetic(payload: CreditEvidenceUpload) -> bool:
    path = Path(__file__).resolve().parent / "outputs" / "demo_scenarios.json"
    if not path.exists():
        return False
    candidate = payload.model_dump(mode="json")
    candidate.pop("borrower_reference", None)
    try:
        scenarios = json.loads(path.read_text(encoding="utf-8"))["scenarios"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    for scenario in scenarios:
        expected = scenario.get("evidence_upload")
        if expected:
            expected = dict(expected)
            expected.pop("borrower_reference", None)
            if expected == candidate:
                return True
    return False


@router.get("/scenarios", dependencies=[Depends(_authorize)])
def list_scenarios():
    path = Path(__file__).resolve().parent / "outputs" / "demo_scenarios.json"
    if not path.exists():
        return {"scenarios": [], "message": "Synthetic examples are not yet packaged."}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"scenarios": [{"id": x["id"], "label": x["label"], "synthetic": True} for x in data["scenarios"]]}


@router.get("/scenarios/{scenario_id}/evidence", dependencies=[Depends(_authorize)])
def get_scenario_evidence(scenario_id: str):
    path = Path(__file__).resolve().parent / "outputs" / "demo_scenarios.json"
    if not path.exists():
        raise HTTPException(404, detail={"code": "SCENARIO_NOT_FOUND"})
    data = json.loads(path.read_text(encoding="utf-8"))
    item = next((x for x in data["scenarios"] if x["id"] == scenario_id), None)
    if item is None:
        raise HTTPException(404, detail={"code": "SCENARIO_NOT_FOUND"})
    return item["evidence_upload"]


@router.post("/applications", dependencies=[Depends(_authorize)])
def create_application(payload: ApplicationCreate):
    conn = _conn()
    try:
        old = conn.execute("SELECT * FROM applications WHERE application_id=?", (payload.application_id,)).fetchone()
        if old:
            if any(old[field] != getattr(payload, field) for field in (
                "borrower_reference", "requested_loan_amount", "loan_purpose",
                "employment_category", "declared_monthly_income", "contact_reference")):
                raise HTTPException(409, detail={"code": "APPLICATION_ID_CONFLICT"})
            return {"application": _as_dict(old), "idempotent_replay": True}
        created = _now()
        conn.execute("INSERT INTO applications VALUES (?,?,?,?,?,?,?,?,0)", (
            payload.application_id, payload.borrower_reference, payload.requested_loan_amount,
            payload.loan_purpose, payload.employment_category, payload.declared_monthly_income,
            payload.contact_reference, created))
        conn.commit()
        row = conn.execute("SELECT * FROM applications WHERE application_id=?", (payload.application_id,)).fetchone()
        return {"application": _as_dict(row), "idempotent_replay": False}
    finally: conn.close()


@router.post("/applications/{application_id}/consent", dependencies=[Depends(_authorize)])
def record_consent(application_id: str, payload: ConsentUpdate):
    conn = _conn()
    try:
        _application(conn, application_id)
        now = _now()
        if payload.grant:
            scopes = sorted(set(payload.scopes))
            if not REQUIRED_SCOPES.issubset(scopes):
                raise HTTPException(422, detail={"code": "REQUIRED_CONSENT_SCOPES_MISSING", "required_scopes": sorted(REQUIRED_SCOPES)})
            state, granted, withdrawn = "GRANTED", now, None
        else:
            scopes, state, granted, withdrawn = [], "WITHDRAWN", None, now
        conn.execute("INSERT INTO consents VALUES (?,?,?,?,?,?) ON CONFLICT(application_id) DO UPDATE SET state=excluded.state,scopes_json=excluded.scopes_json,granted_at=excluded.granted_at,withdrawn_at=excluded.withdrawn_at,updated_at=excluded.updated_at",
                     (application_id, state, json.dumps(scopes), granted, withdrawn, now))
        conn.commit()
        return {"application_id": application_id, "state": state, "scopes": scopes,
                "granted_at": granted, "withdrawn_at": withdrawn, "updated_at": now}
    finally: conn.close()


@router.post("/applications/{application_id}/evidence", dependencies=[Depends(_authorize)])
def submit_evidence(application_id: str, file: UploadFile = File(...)):
    conn = _conn()
    try:
        app_row = _application(conn, application_id)
        consent = conn.execute("SELECT * FROM consents WHERE application_id=?", (application_id,)).fetchone()
        if consent is None or consent["state"] != "GRANTED" or consent["withdrawn_at"] is not None or not REQUIRED_SCOPES.issubset(set(json.loads(consent["scopes_json"]))):
            raise HTTPException(403, detail={"code": "CONSENT_REQUIRED"})
    finally: conn.close()
    name = _safe_name(file.filename)
    if not name.lower().endswith(".json") or file.content_type not in {"application/json", "text/json", "application/octet-stream"}:
        raise HTTPException(415, detail={"code": "SUPPORTED_EVIDENCE_MUST_BE_JSON"})
    raw = file.file.read(MAX_EVIDENCE_BYTES + 1)
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise HTTPException(413, detail={"code": "EVIDENCE_FILE_TOO_LARGE", "max_bytes": MAX_EVIDENCE_BYTES})
    try: body = CreditEvidenceUpload.model_validate_json(raw)
    except Exception as exc:
        raise HTTPException(422, detail={"code": "INVALID_EVIDENCE_JSON", "message": str(exc)[:300]}) from exc
    if body.borrower_reference != app_row["borrower_reference"]:
        raise HTTPException(409, detail={"code": "BORROWER_ACCOUNT_LINK_MISMATCH"})
    if body.evidence_type == "CREDIT_ACCOUNT_REPAYMENT" and body.borrower_account_count != 1:
        raise HTTPException(422, detail={"code": "MULTI_ACCOUNT_AGGREGATION_UNRESOLVED"})
    evidence_id = "EVD_" + uuid.uuid4().hex
    now = _now(); digest = sha256(raw).hexdigest().upper()
    is_synthetic = _is_packaged_synthetic(body)
    conn = _conn()
    try:
        conn.execute("INSERT INTO evidence (evidence_id,application_id,evidence_type,filename,sha256,payload_json,submitted_at,synthetic_demo) VALUES (?,?,?,?,?,?,?,?)",
                     (evidence_id, application_id, body.evidence_type, name, digest, body.model_dump_json(), now, int(is_synthetic)))
        conn.commit()
    finally: conn.close()
    return {"evidence_id": evidence_id, "application_id": application_id, "evidence_type": body.evidence_type,
            "filename": name, "sha256": digest, "bytes": len(raw), "status": "EVIDENCE_STORED", "submitted_at": now,
            "synthetic_demo": is_synthetic}


@router.post("/applications/{application_id}/assess", dependencies=[Depends(_authorize)])
def assess_application(application_id: str):
    if os.getenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(404, detail={"code": "EXPERIMENTAL_FEATURE_DISABLED"})
    conn = _conn()
    try:
        app = _application(conn, application_id)
        consent = conn.execute("SELECT * FROM consents WHERE application_id=?", (application_id,)).fetchone()
        evidence = conn.execute("SELECT * FROM evidence WHERE application_id=? ORDER BY submitted_at DESC LIMIT 1", (application_id,)).fetchone()
        if consent is None or consent["state"] != "GRANTED" or consent["withdrawn_at"] is not None or not REQUIRED_SCOPES.issubset(set(json.loads(consent["scopes_json"]))):
            raise HTTPException(403, detail={"code": "CONSENT_REQUIRED"})
        if evidence is None: raise HTTPException(422, detail={"code": "CREDIT_ACCOUNT_EVIDENCE_REQUIRED"})
        payload = CreditEvidenceUpload.model_validate_json(evidence["payload_json"])
        if payload.evidence_type != "CREDIT_ACCOUNT_REPAYMENT":
            result = {"status":"INSUFFICIENT_CREDIT_ACCOUNT_EVIDENCE","decision_use":"NOT_FOR_CREDIT_DECISION",
                     "eligibility":{"eligible":False,"blocking_reasons":["BANK_STATEMENT_ALONE_CANNOT_SUPPLY_CREDIT_ACCOUNT_REPAYMENT_FEATURES"]},
                     "features":None,"scorecard":None,"reason_codes":[],"limitations":["NO_SCORE_GENERATED"]}
        else:
            if len(payload.statements)!=6 or len(payload.repayment_history)!=6:
                result = {"status":"INSUFFICIENT_CREDIT_ACCOUNT_EVIDENCE","decision_use":"NOT_FOR_CREDIT_DECISION",
                     "eligibility":{"eligible":False,"blocking_reasons":["SIX_MONTHS_OF_STATEMENTS_AND_EXPLICIT_REPAYMENT_HISTORY_REQUIRED"]},
                     "features":None,"scorecard":None,"reason_codes":[],"limitations":["NO_SCORE_GENERATED"]}
            else:
                from phase2.shadow_api.routes import ShadowAssessmentRequest, _build_response
                from phase2.shadow_api.routes import REQUIRED_SCOPES as API_SCOPES
                from phase2.shadow_scorecard.artifacts import load_scorecard
                request = ShadowAssessmentRequest.model_validate({
                    "borrower_reference":payload.borrower_reference,
                    "prediction_cutoff_month":payload.prediction_cutoff_month,
                    "statements":payload.statements,"repayment_history":payload.repayment_history,
                    "consent":{"state":"GRANTED","scopes":sorted(API_SCOPES),"granted_at":consent["granted_at"]},
                    "borrower_account_count":payload.borrower_account_count})
                result = _build_response(request, debug=True)
                if result.get("eligibility",{}).get("eligible"):
                    artifact = load_scorecard(SCORECARD)
                    from phase2.shadow_scorecard.scorer import score_validated_result
                    # Re-run the pure frozen scorer through the validated Phase 2E object for full bin/contribution trace.
                    from phase2.credit_parser.normalizer import run_equivalence_path
                    from phase2.credit_evidence.models import Consent, ConsentState
                    consent_obj=Consent(ConsentState.GRANTED,frozenset(API_SCOPES),datetime.fromisoformat(consent["granted_at"]))
                    parsed=run_equivalence_path(payload.statements,payload.repayment_history,consent=consent_obj,
                        prediction_cutoff_month=payload.prediction_cutoff_month,borrower_reference=payload.borrower_reference,
                        at=datetime.now(timezone.utc))
                    trace=score_validated_result(parsed,artifact=artifact)
                    result["trace"]=trace
                    result["scorecard"]["score_label"]="PRISM Experimental Score"
        # Fraud is evaluated and persisted independently for scoreable and blocked cases.
        result["fraud_risk"]=_fraud_for_application(conn,app)
        result["synthetic_demo"] = bool(evidence["synthetic_demo"])
        assessed_at=_now(); assessment_id="ASM_"+uuid.uuid4().hex
        status_label=result.get("status","ASSESSMENT_FAILED")
        model_id=None
        if result.get("scorecard"):
            model_id=result["trace"].get("artifact_sha256")
        conn.execute("INSERT INTO assessments VALUES (?,?,?,?,?,?,?)", (assessment_id,application_id,evidence["evidence_id"],status_label,model_id,
                     json.dumps(result,sort_keys=True,allow_nan=False),assessed_at))
        conn.commit()
        return {"assessment_id":assessment_id,"application_id":application_id,"assessment_status":status_label,
                "assessed_at":assessed_at,"synthetic_demo":bool(evidence["synthetic_demo"]),"result":result}
    finally: conn.close()


def _fraud_for_application(conn, app):
    from fraud.integration import assess_fraud
    history=[dict(x) for x in conn.execute("SELECT application_id,borrower_reference AS borrower_id,created_at AS application_date,'SUBMITTED' AS status FROM applications WHERE borrower_reference=? AND application_id<>? ORDER BY created_at DESC LIMIT 20",
        (app["borrower_reference"],app["application_id"]))]
    return assess_fraud(borrower={"borrower_id":app["borrower_reference"],"application_id":app["application_id"],"application_date":app["created_at"],"status":"SUBMITTED"},
        application_history=history,transactions=[],reference_time=datetime.now(timezone.utc))


@router.get("/applications", dependencies=[Depends(_authorize)])
def list_applications():
    conn = _conn()
    try:
        rows=conn.execute("""SELECT a.*, COALESCE(c.state,'MISSING') consent_state,
          (SELECT COUNT(*) FROM evidence e WHERE e.application_id=a.application_id) evidence_count,
          (SELECT status FROM assessments x WHERE x.application_id=a.application_id ORDER BY assessed_at DESC LIMIT 1) latest_status,
          (SELECT result_json FROM assessments x WHERE x.application_id=a.application_id ORDER BY assessed_at DESC LIMIT 1) latest_result_json
          FROM applications a LEFT JOIN consents c ON c.application_id=a.application_id ORDER BY a.created_at DESC LIMIT 200""").fetchall()
        items=[]
        for row in rows:
            item=dict(row);raw=item.pop("latest_result_json",None);item["latest_result"]=json.loads(raw) if raw else None;items.append(item)
        return {"applications":items,"count":len(items)}
    finally: conn.close()


@router.get("/applications/{application_id}", dependencies=[Depends(_authorize)])
def get_application(application_id: str):
    conn=_conn()
    try:
        app=dict(_application(conn,application_id))
        app["consent"]=_as_dict(conn.execute("SELECT * FROM consents WHERE application_id=?",(application_id,)).fetchone())
        app["evidence"]=[{k:row[k] for k in ("evidence_id","evidence_type","filename","sha256","submitted_at","synthetic_demo")} for row in conn.execute("SELECT * FROM evidence WHERE application_id=? ORDER BY submitted_at",(application_id,))]
        app["assessments"]=[{"assessment_id":r["assessment_id"],"status":r["status"],"assessed_at":r["assessed_at"],"result":json.loads(r["result_json"])} for r in conn.execute("SELECT * FROM assessments WHERE application_id=? ORDER BY assessed_at",(application_id,))]
        return {"application":app}
    finally: conn.close()


@router.delete("/applications/{application_id}", dependencies=[Depends(_authorize)])
def delete_application(application_id: str):
    conn=_conn()
    try:
        _application(conn,application_id)
        conn.execute("DELETE FROM applications WHERE application_id=?",(application_id,));conn.commit()
        return {"application_id":application_id,"deleted":True}
    finally: conn.close()


def readiness():
    if not SCORECARD.exists() or not SCORECARD_MANIFEST.exists():
        return False,{"code":"FROZEN_SCORECARD_MISSING"}
    manifest=json.loads(SCORECARD_MANIFEST.read_text(encoding="utf-8-sig"))
    digest=sha256(SCORECARD.read_bytes()).hexdigest().upper()
    if digest!=manifest.get("sha256"):
        return False,{"code":"FROZEN_SCORECARD_HASH_MISMATCH","expected":manifest.get("sha256"),"actual":digest}
    try:
        from phase2.shadow_scorecard.artifacts import FEATURE_ORDER, load_scorecard
        card=load_scorecard(SCORECARD)
        if card.get("feature_order") != FEATURE_ORDER:
            return False,{"code":"FROZEN_SCORECARD_FEATURE_ORDER_INVALID"}
    except Exception as exc:
        return False,{"code":"FROZEN_SCORECARD_UNREADABLE","message":str(exc)[:200]}
    try:
        conn=_conn()
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except Exception as exc:
        return False,{"code":"DEMO_DATABASE_UNAVAILABLE","message":str(exc)[:200]}
    return True,{"scorecard_sha256":digest,"scorecard":"loaded_and_verified","database":"connected"}
