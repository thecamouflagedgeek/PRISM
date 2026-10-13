"""Borrower-owned workflow for the separate experimental cash-flow health index."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4
import re
import logging

import fitz
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.session_store import get_session
from database.db import get_db
from database.models import (Application, AuditEvent, BankCashflowAssessment,
                             Consent, Document, ExperimentalAssessment, RiskScore)
from database.crud import save_document
from features.bank_health_index import (ASSESSMENT_TYPE, INDEX_VERSION,
    calculate_bank_health_index, simulate_bank_health, score_observed_month)
from route.experimental_assessment_routes import _session_owner
from services.ocr_service import get_ocr_engine
from core.demo_receipt import record_demo_receipt
from fraud.integration import assess_fraud
from features.thin_file_score import calculate_cashflow_snapshot, simulate_cashflow_snapshot, SNAPSHOT_VERSION

router = APIRouter(prefix="/assess/bank-cashflow", tags=["Experimental Bank Cashflow Assessment"])
MAX_FILES = 12
MAX_FILE_BYTES = 15 * 1024 * 1024
logger = logging.getLogger("uvicorn.error")


def _supporting(file, category, app, db, ocr_engine):
    from phase2.credit_parser.document_extraction import extract_document_text
    from ingestion.identity import extract_person_name
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in {'.pdf', '.jpg', '.jpeg', '.png'}:
        raise HTTPException(415, "Unsupported supporting document format")
    data = file.file.read(MAX_FILE_BYTES + 1)
    if not data or len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "Each supporting document must be between 1 byte and 15 MB")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp.write(data)
    try:
        doc = db.query(Document).filter_by(application_id=app.application_id, document_hash=sha256(data).hexdigest()).first()
        if doc is None:
            doc = save_document(db, app.application_id, category, file.filename or 'supporting', temp.name,
                                parser_version='supporting-v1')
        text, method, confidence, pages = extract_document_text(temp.name, ocr_engine)
        labels = ({'payroll month': 'salary_period', 'net salary': 'net_salary',
            'employer': 'employer', 'employee id': 'employee_reference'} if category == 'SALARY'
            else {'billing period': 'billing_period', 'due date': 'due_date',
            'payment date': 'payment_date', 'consumer reference': 'service_reference'})
        fields, provenance = {}, {}
        page = 1
        for line_no, line in enumerate(text.splitlines(), 1):
            if '\f' in line: page += 1
            if ':' not in line: continue
            key, value = line.split(':', 1)
            field = labels.get(key.strip().lower())
            if field:
                fields[field] = value.strip()
                provenance[field] = {'page': page, 'line': line_no}
        if category == 'SALARY' and 'net_salary' in fields:
            fields['net_salary'] = float(re.sub(r'[^\d.]', '', fields['net_salary']))
        table_labels = ({'Gross pay': 'gross_salary', 'Total deductions': 'deductions'}
                        if category == 'SALARY' else {'TOTAL BILL': 'amount_due', 'Payment status': 'payment_status'})
        source_lines = text.splitlines()
        for label, field in table_labels.items():
            for i, line in enumerate(source_lines):
                if line.strip().casefold() != label.casefold(): continue
                following = source_lines[i+1:i+4]
                if field == 'payment_status':
                    value = next((v for v in following if re.match(r'^(?:PAID|UNPAID|PENDING)\b', v, re.I)), None)
                else:
                    match = re.search(r'\bINR\s+([\d,]+\.\d{2})', '\n'.join(following))
                    value = float(match[1].replace(',', '')) if match else None
                if value is not None:
                    fields[field] = value
                    provenance[field] = {'page': 1 + text[:text.find(line)].count('\f'), 'line': i+1}
                    break
        labels.update(table_labels)
        expected_header = r'\b(?:salary slip|payslip)\b' if category == 'SALARY' else r'\b(?:utility bill|electricity.*bill|water bill)\b'
        if not re.search(expected_header, text, re.I):
            fields = {}
        gaps = [f'MISSING_FIELD:{field}' for field in labels.values() if field not in fields]
        doc.processing_status = 'PARTIALLY_EXTRACTED' if gaps else 'EXTRACTED'
        db.commit()
        return {'document_id': doc.document_id, 'file_name': file.filename, 'document_type': category,
            'extraction_method': method, 'page_count': pages, 'fields': fields,
            'field_provenance': provenance, 'findings': gaps,
            'assessment_role': 'SUPPORTING_ONLY_NOT_MODEL_INPUT',
            '_identity_name': extract_person_name(text)}
    except (ValueError, RuntimeError, fitz.FileDataError):
        db.rollback()
        return {'document_id': doc.document_id, 'file_name': file.filename, 'document_type': category,
                'findings': ['UNREADABLE_OR_INVALID_SUPPORTING_DOCUMENT']}
    finally:
        os.unlink(temp.name)


def _supporting_review(file, category, app, db, engine):
    try:
        return _supporting(file, category, app, db, engine)
    except HTTPException as error:
        db.rollback()
        return {'document_id': None, 'file_name': file.filename, 'document_type': category,
            'assessment_role': 'SUPPORTING_ONLY_NOT_MODEL_INPUT', 'findings': [f'SUPPORTING_DOCUMENT_REJECTED:{error.status_code}']}


class ScenarioRequest(BaseModel):
    monthly_income: float | None = None
    monthly_expenses: float | None = None
    monthly_debt_obligations: float | None = None
    average_balance: float | None = None
    income_volatility: float | None = None


@router.post('/preview')
async def preview_bank_statements(statement_files: list[UploadFile] = File(...),
        statement_password: str | None = Form(None), session_id: str = Header(...),
        db: Session = Depends(get_db)):
    """Owned, consented extraction review; never calculates or edits a score."""
    session, app = _session_owner(session_id, db)
    consent = db.query(Consent).filter_by(application_id=app.application_id).first()
    if not consent or not consent.bank_consent or not consent.dpdpa_consent:
        raise HTTPException(403, 'Recorded bank consent is required')
    if not 1 <= len(statement_files) <= MAX_FILES:
        raise HTTPException(422, 'Select between 1 and 12 statements')
    output = []
    for file in statement_files:
        _, _, tx, meta, finding = _ingest(file, session, app, db, get_ocr_engine(), password=statement_password)
        meta['source_document_id'] = str(finding['document_id'])
        finding.update({'total_credits':float(tx.loc[tx.type.eq('CR'),'amount'].sum()),
            'total_debits':float(tx.loc[tx.type.eq('DR'),'amount'].sum()),
            'opening_balance':meta.get('opening_balance'),'closing_balance':meta.get('statement_closing_balance'),
            'balances_reconciled':_balance_validation(tx,[meta]),
            'transactions':[{'date':str(r.date)[:10],'amount':float(r.amount),'direction':r.type,
                'running_balance':float(r.closing_balance),'source_page':int(r.source_page)} for r in tx.itertuples()]})
        output.append(finding)
    from database.crud import save_audit_event
    save_audit_event(db, app.application_id, 'bank_extraction_review', 'bank_statement', 'success')
    return {'state':'Review Required','documents':output,
        'message':'Review the extracted values against the source. This preview is not an assessment. Missing or inconsistent evidence must be resolved before scoring.'}


def _payload(row: BankCashflowAssessment) -> dict:
    result = dict(row.result_json or {})
    result.update({"assessment_id": row.assessment_id, "application_id": row.application_id,
        "assessment_type": ASSESSMENT_TYPE, "model_version": row.model_version,
        "assessment_timestamp": row.created_at.replace(tzinfo=timezone.utc).isoformat(),
        "score": row.score, "pd": None})
    return result


def _ingest(file: UploadFile, session, app, db, ocr_engine, password=None):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise HTTPException(415, f"Unsupported bank statement format: {suffix or 'no extension'}")
    data = file.file.read(MAX_FILE_BYTES + 1)
    if not data or len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "Each statement must be between 1 byte and 15 MB")
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        temp.write(data); temp.close()
        digest = sha256(data).hexdigest()
        doc = db.query(Document).filter_by(application_id=app.application_id, document_hash=digest).first()
        if doc is None:
            doc = save_document(db, app.application_id, "BANK_STATEMENT", file.filename or "statement", temp.name,
                                parser_version="bank-index-v1")
        from route.assessment_routes import process_bank_doc
        features, tx, metadata = process_bank_doc(temp.name, ocr_engine, password=password)
        if len(tx) and "source_page" not in tx:
            tx["source_page"] = 1
        if len(tx) and "source_line" not in tx:
            tx["source_line"] = None
        tx = tx.copy()
        tx["source_document_id"] = str(doc.document_id)
        metadata = dict(metadata)
        doc.processing_status = "EXTRACTED"
        db.commit()
        finding = {"document_id": doc.document_id, "file_name": file.filename,
            "detected_bank":metadata.get('detected_bank'),
            "document_type": "BANK_STATEMENT", "extraction_method": metadata.get("method"),
            "extraction_confidence": metadata.get("extraction_confidence"),
            "quality_score": metadata.get("quality_score"), "valid_transaction_coverage": metadata.get("valid_transaction_coverage"),
            "page_count": metadata.get("page_count"), "transaction_count": len(tx),
            "currency": metadata.get("currency"), "account_reference_available": bool(metadata.get("account_reference_token")),
            "statement_period": metadata.get("statement_period"),
            "opening_balance_available": metadata.get("opening_balance") is not None,
            "statement_closing_balance_available": metadata.get("statement_closing_balance") is not None,
            "declared_page_sequence_complete": metadata.get("declared_page_sequence_complete"),
            "declared_page_count": metadata.get('declared_page_count'),
            "processing_trace": ['UPLOAD_RECEIVED','DOCUMENT_CLASSIFIED','PDF_EXTRACTED','FIELDS_PARSED'],
            "source_provenance": [{"source_document_id": int(doc.document_id), "source_page": int(r.source_page),
                "source_line": int(r.source_line) if pd.notna(r.source_line) else None}
                for r in tx.itertuples() if pd.notna(r.source_page)],
            "findings": list(metadata.get("diagnostics") or [])}
        return doc, digest, tx, metadata, finding
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        # Never include parser exceptions containing document content in an API response or log.
        state = 'Document Could Not Be Read' if 'DOCUMENT_COULD_NOT_BE_READ' in str(exc) else 'Review Required'
        raise HTTPException(422, f"{state}: upload a readable statement with clear dated debit, credit and balance columns. For an encrypted PDF, enter its password. No score was generated.") from exc
    finally:
        try: os.unlink(temp.name)
        except OSError: pass


def _chronological_statement_rows(group: pd.DataFrame) -> pd.DataFrame:
    """Preserve source order within a day, reversing a newest-first ledger whole."""
    group = group.sort_values(['source_page', 'source_line'], kind='stable', na_position='last')
    dates = pd.to_datetime(group.date, errors='coerce', dayfirst=True)
    if dates.is_monotonic_decreasing and not dates.is_monotonic_increasing:
        return group.iloc[::-1]
    return group


def _observed_balance_validation(tx: pd.DataFrame) -> bool:
    """Verify successive source balances; never infer a declared opening balance."""
    import numpy as np
    for _, group in tx.groupby('source_document_id', dropna=False):
        group = _chronological_statement_rows(group)
        if len(group) < 2:
            return False
        balances = pd.to_numeric(group.closing_balance, errors='coerce').to_numpy(float)
        amounts = pd.to_numeric(group.amount, errors='coerce').to_numpy(float)
        signs = group.type.map({'CR': 1, 'DR': -1}).to_numpy(float)
        if not (np.isfinite(balances).all() and np.isfinite(amounts).all() and np.isfinite(signs).all()):
            return False
        if (amounts < 0).any() or not (abs(np.diff(balances) - (amounts * signs)[1:]) <= .05).all():
            return False
    return len(tx) >= 2


def _balance_validation(tx: pd.DataFrame, metadata: list[dict]) -> bool | None:
    if len(tx) < 1 or "closing_balance" not in tx:
        return None
    frame = tx.copy()
    frame["date"] = pd.to_datetime(frame.date, errors="coerce", dayfirst=True)
    frame["amount"] = pd.to_numeric(frame.amount, errors="coerce").abs()
    frame["closing_balance"] = pd.to_numeric(frame.closing_balance, errors="coerce")
    metadata_by_doc = {str(item.get("source_document_id")): item for item in metadata}
    if not all(item.get("opening_balance") is not None and item.get("statement_closing_balance") is not None for item in metadata):
        return None
    periods = sorted(metadata, key=lambda item: (item.get('statement_period') or {}).get('start', ''))
    for left, right in zip(periods, periods[1:]):
        if left.get('statement_period') and right.get('statement_period'):
            if abs(float(left['statement_closing_balance']) - float(right['opening_balance'])) > .05:
                return False
    for document_id, group in frame.groupby("source_document_id", dropna=False):
        group = _chronological_statement_rows(group)
        if group[["date", "amount", "closing_balance"]].isna().any().any(): return False
        balances = group.closing_balance.to_numpy(dtype=float)
        signs = group.type.astype(str).str.upper().map({"CR": 1, "DR": -1})
        if signs.isna().any(): return False
        changes = group.amount.to_numpy(dtype=float) * signs.to_numpy(dtype=float)
        source = metadata_by_doc.get(str(document_id), {})
        if abs((float(source["opening_balance"]) + changes[0]) - balances[0]) > 0.05:
            return False
        if len(balances) > 1 and not (abs((balances[1:] - balances[:-1]) - changes[1:]) <= 0.05).all():
            return False
        if abs(balances[-1] - float(source["statement_closing_balance"])) > 0.05:
            return False
    return True


def _months_fully_covered(metadata: list[dict], months: list[str]) -> bool:
    periods = [m.get("statement_period") for m in metadata]
    if not periods or any(not p or not p.get("start") or not p.get("end") for p in periods):
        return False
    intervals = sorted((pd.Timestamp(p["start"]), pd.Timestamp(p["end"])) for p in periods)
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1] + pd.Timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    for month in months:
        start = pd.Period(month, freq="M").start_time
        end = pd.Period(month, freq="M").end_time.normalize()
        if not any(left <= start and right >= end for left, right in merged):
            return False
    return bool(months)


def _ordered_transactions(frames: list[pd.DataFrame]) -> bool:
    if not frames:
        return False
    for frame in frames:
        dates = pd.to_datetime(frame["date"], errors="coerce", dayfirst=True).dropna()
        if len(dates) < 2: return False
        changes = dates.diff().dropna().dt.total_seconds()
        if not (changes.ge(0).all() or changes.le(0).all()): return False
    return True


def _single_month_snapshot_order_valid(tx: pd.DataFrame, metadata: list[dict]) -> bool:
    """Permit source-row order for a one-month snapshot when the ledger balances prove it.

    Some bank statements list posted dates out of calendar order while preserving
    their ledger row order. Snapshot scoring aggregates one month, so this is safe
    only for a single statement, one observed month, valid dates, and a reconciled
    source-order running-balance chain.
    """
    if len(metadata) != 1 or not {'source_page', 'source_line'}.issubset(tx.columns):
        return False
    if tx[['source_page', 'source_line']].isna().any().any():
        return False
    dates = pd.to_datetime(tx.date, errors='coerce', dayfirst=True)
    if dates.isna().any() or dates.dt.to_period('M').nunique() != 1:
        return False
    period = metadata[0].get('statement_period')
    if period and period.get('start') and period.get('end'):
        start, end = pd.Timestamp(period['start']), pd.Timestamp(period['end'])
        if (dates.lt(start).any() or dates.gt(end).any()):
            return False
    return _observed_balance_validation(tx)


@router.post("")
async def assess_bank_cashflow(statement_files: list[UploadFile] = File(...),
        salary_files: list[UploadFile] = File(default=[]), utility_files: list[UploadFile] = File(default=[]),
        assessment_profile: str = Form('history'), statement_password: str | None = Form(None),
        session_id: str = Header(...), db: Session = Depends(get_db)):
    if assessment_profile not in {'history','snapshot','auto'}:
        raise HTTPException(422, 'Choose a supported bank assessment profile')
    if not statement_files or len(statement_files) > MAX_FILES:
        raise HTTPException(422, f"Upload between 1 and {MAX_FILES} bank statements")
    session, app = _session_owner(session_id, db)
    request_id = str(uuid4())
    logger.info("assessment request_id=%s application_id=%s type=%s files=%s category=BANK stage=received",
                request_id, app.application_id, ASSESSMENT_TYPE, len(statement_files))
    consent = db.query(Consent).filter_by(application_id=app.application_id).first()
    if not consent or not consent.bank_consent or not consent.dpdpa_consent:
        raise HTTPException(403, "Recorded bank-statement and personal-data processing consent is required")
    record_demo_receipt(app.application_id, '/assess/bank-cashflow', {
        'statement_files': statement_files, 'salary_files': salary_files, 'utility_files': utility_files})
    if len(salary_files) > MAX_FILES or len(utility_files) > MAX_FILES:
        raise HTTPException(422, "Upload at most 12 files per supporting category")
    missing_support_consent = []
    if salary_files and not consent.salary_consent: missing_support_consent.append('salary')
    if utility_files and not consent.utility_consent: missing_support_consent.append('utility')
    if missing_support_consent:
        logger.warning("assessment request_id=%s application_id=%s stage=consent_blocked categories=%s",
                       request_id, app.application_id, ','.join(missing_support_consent))
        raise HTTPException(403, "Salary or utility files were included without consent. Remove those optional files, or enable their consent on the consent page. Your bank-only assessment does not require them.")
    engine = get_ocr_engine()
    supporting_documents = [_supporting_review(file, category, app, db, engine)
        for category, files in [('SALARY', salary_files), ('UTILITY', utility_files)] for file in files]
    docs, digests, frames, metadata, findings = [], [], [], [], []
    for file in statement_files:
        doc, digest, tx, meta, finding = _ingest(file, session, app, db, engine, password=statement_password)
        docs.append(doc); digests.append(digest); frames.append(tx); metadata.append(meta); findings.append(finding)
    from ingestion.identity import verify_document_identities
    identity_check = verify_document_identities(metadata, supporting_documents)
    if not identity_check['verified']:
        problem = ('The names on these selected documents do not match: ' + ', '.join(identity_check['mismatched_documents'])
                   if identity_check['status'] == 'MISMATCH' else
                   'PRISM could not verify a name on: ' + ', '.join(identity_check['unverified_documents']))
        raise HTTPException(422, 'IDENTITY_CHECK_FAILED: ' + problem +
            '. Upload documents for the same applicant, or use a clearer document with a readable name. No score was generated.')
    tx = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    tokens = {m.get("account_reference_token") for m in metadata}
    tokens.discard(None)
    account_linked = len(tokens) == 1 and all(m.get("account_reference_token") for m in metadata)
    currencies = {m.get("currency") for m in metadata}
    currency = next(iter(currencies)) if len(currencies) == 1 and None not in currencies else None
    ambiguous = any(m.get("currency_ambiguous") for m in metadata)
    duplicates = tx.duplicated(subset=[c for c in ["date", "amount", "type", "narration", "closing_balance"] if c in tx], keep=False)
    narration = tx.get("narration", pd.Series("", index=tx.index)).fillna("").astype(str)
    internal_transfer = narration.str.contains(r"\b(?:own account|self transfer|internal transfer|between own accounts)\b", case=False, regex=True)
    adjustment = narration.str.contains(r"\b(?:refund|reversal|chargeback|reversed|cancelled transaction)\b", case=False, regex=True)
    for m, doc in zip(metadata, docs): m["source_document_id"] = str(doc.document_id)
    evidence = {"account_linked": account_linked, "balance_reconciled": _balance_validation(tx, metadata),
        "observed_running_balances_reconciled": _observed_balance_validation(tx),
        "duplicate_ambiguity": bool(duplicates.any()),
        "page_coverage_complete": all(m.get("declared_page_sequence_complete") is True for m in metadata),
        "complete_month_coverage": _months_fully_covered(metadata,
            sorted(pd.to_datetime(tx.date, errors="coerce", dayfirst=True).dropna().dt.to_period("M").astype(str).unique().tolist())),
        "transaction_order_valid": (_ordered_transactions(frames) if assessment_profile == 'history' else (
            all(len(frame) == 1 and pd.to_datetime(frame['date'], errors='coerce').notna().all()
                or _ordered_transactions([frame]) for frame in frames)
            or _single_month_snapshot_order_valid(tx, metadata))),
        "non_cashflow_adjustments_clear": not bool((internal_transfer | adjustment).any()),
        "internal_transfer_rows_requiring_review": int(internal_transfer.sum()),
        "refund_reversal_rows_requiring_review": int(adjustment.sum()),
        "source_document_ids": [d.document_id for d in docs], "extraction_methods": sorted({m.get("method", "unknown") for m in metadata}),
        "extraction_quality_min": min((float(m.get("quality_score", 0)) for m in metadata), default=0),
        "account_reference_token_present": account_linked, "duplicate_rows_detected": int(duplicates.sum())}
    if ambiguous: evidence["page_coverage_complete"] = False
    if internal_transfer.any(): findings.append({"findings": ["Internal-transfer-like rows require review and were not scored."]})
    if adjustment.any(): findings.append({"findings": ["Refund/reversal-like rows require review and were not scored."]})
    history = calculate_bank_health_index(tx, currency=currency, evidence=evidence) if assessment_profile == 'auto' else None
    if history and history.get('score') is not None:
        result = history
        result['assessment_profile'] = 'history'
    elif assessment_profile in {'snapshot','auto'}:
        try:
            result = calculate_cashflow_snapshot(tx, currency=currency, evidence=evidence, document_count=len(statement_files))
        except ValueError as error:
            issues = str(error).split('Checks requiring correction:')[-1].strip()
            if 'Checks requiring correction:' in str(error):
                issues = '; '.join(part.strip().replace('_',' ').capitalize() for part in issues.split(','))
            raise HTTPException(422, 'Review Required: '+issues+'. Replace or complete the affected bank statement; no score was generated.') from error
    else:
        result = calculate_bank_health_index(tx, currency=currency, evidence=evidence)
    # Independent transaction review: never changes credit PD or bank index.
    result['fraud_findings'] = assess_fraud(transactions=tx)
    trend = tx.copy()
    trend['month'] = pd.to_datetime(trend['date'], errors='coerce', format='mixed', dayfirst=True).dt.to_period('M').astype(str)
    result['monthly_balance_trend'] = [{'month':month,'average_balance':round(float(group.closing_balance.mean()),2),
        'minimum_balance':float(group.closing_balance.min()),'maximum_balance':float(group.closing_balance.max())}
        for month,group in trend.groupby('month',sort=True)]
    result['fraud_findings']['coverage'] = {
        'transactions_reviewed': len(tx), 'transaction_rules': 'evaluated',
        'identity_and_loan_stacking': 'not assessed: verified identity/history unavailable'}
    for finding in findings:
        finding.update({'account_linked': account_linked, 'validation_result': result['validation_status'],
            'rejection_reasons': result.get('evidence_gaps', [])})
    result['processing_trace'] = ['UPLOAD_RECEIVED','DOCUMENT_CLASSIFIED','PDF_EXTRACTED','FIELDS_PARSED','EVIDENCE_AGGREGATED'] + (
        ['VALIDATION_PASSED','FEATURES_COMPUTED','SCORE_COMPUTED','ASSESSMENT_PERSISTED'] if result.get('score') is not None else ['VALIDATION_FAILED','ASSESSMENT_PERSISTED'])
    result['aggregation_receipt'] = {'bank_documents': len(statement_files), 'supporting_documents': len(salary_files)+len(utility_files),
        'transactions_parsed': len(tx), 'debits_parsed': int(tx.type.eq('DR').sum()), 'credits_parsed': int(tx.type.eq('CR').sum()),
        'account_linked': account_linked, 'balances_reconciled': evidence['balance_reconciled'],
        'identity_check':identity_check['status']}
    result["document_findings"] = findings
    result['supporting_documents'] = [{key:value for key,value in item.items() if key != '_identity_name'}
        for item in supporting_documents]
    result["decision_use"] = "NOT_FOR_CREDIT_DECISION"
    result_version = result['model_version']
    identity = {"application_id": app.application_id, "input_hashes": sorted(digests), "version": result_version,
        "parser_version": "native-coordinate-v7", "supporting_document_ids": sorted(item['document_id'] for item in result['supporting_documents'] if item.get('document_id')),
        "consent_scope": "BANK_CASHFLOW_EXPERIMENTAL"}
    input_hash = sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    row = db.query(BankCashflowAssessment).filter_by(application_id=app.application_id, input_sha256=input_hash).first()
    created = row is None
    if row is None:
        now = datetime.utcnow()
        row = BankCashflowAssessment(assessment_id=str(uuid4()), application_id=app.application_id,
            user_id=session.user_id, input_sha256=input_hash, assessment_type=ASSESSMENT_TYPE,
            model_version=result_version, assessment_status=result["status"],
            evidence_document_ids=[d.document_id for d in docs], feature_values=result.get("feature_values", {}),
            score=result.get("score"), probability_default=None,
            feature_contributions=result.get("feature_contributions", []), reason_codes=result.get("reason_codes", []),
            validation_status=result.get("validation_status", "INCOMPLETE"), result_json=result, created_at=now)
        db.add(row)
        db.add(AuditEvent(application_id=app.application_id, action="bank_cashflow_assessment_created",
            entity="bank_cashflow_assessment", status="scored" if row.score is not None else "insufficient", event_timestamp=now,
            details={"assessment_id": row.assessment_id, "assessment_type": ASSESSMENT_TYPE,
                     "model_version": INDEX_VERSION, "source_document_count": len(docs), "score_generated": row.score is not None}))
        try:
            db.commit(); db.refresh(row)
        except Exception:
            db.rollback()
            row = db.query(BankCashflowAssessment).filter_by(application_id=app.application_id, input_sha256=input_hash).first()
            if row is None: raise
            created = False
    response = _payload(row); response["idempotent_replay"] = not created
    response['request_id'] = request_id
    db.add(AuditEvent(application_id=app.application_id, action='bank_cashflow_assessment_checked',
        entity='bank_cashflow_assessment', status='scored' if row.score is not None else 'review',
        event_timestamp=datetime.utcnow(), details={'assessment_id':row.assessment_id,
            'source_document_count':len(docs),'score_generated':row.score is not None}))
    db.commit()
    logger.info("assessment request_id=%s application_id=%s type=%s files=%s stage=complete outcome=%s",
                request_id, app.application_id, ASSESSMENT_TYPE, len(statement_files), row.assessment_status)
    return response


@router.get("/latest")
def latest_bank_cashflow(session_id: str = Header(...), db: Session = Depends(get_db)):
    session, app = _session_owner(session_id, db)
    row = db.query(BankCashflowAssessment).filter_by(application_id=app.application_id, user_id=session.user_id).order_by(BankCashflowAssessment.score.isnot(None).desc(), BankCashflowAssessment.created_at.desc(), BankCashflowAssessment.assessment_id.desc()).first()
    if row is None: raise HTTPException(404, "No bank cash-flow assessment exists for this application")
    return _payload(row)


@router.get("/history")
def borrower_assessment_history(session_id: str = Header(...), db: Session = Depends(get_db)):
    """Return saved borrower assessments and statement dates for the signed-in user."""
    session, application = _session_owner(session_id, db)
    application_ids = [row[0] for row in db.query(Application.application_id)
        .filter(Application.user_id == session.user_id).all()]
    if not application_ids:
        return {"application_id": application.application_id, "assessments": [], "monthly_scores": []}

    documents = db.query(Document).filter(Document.application_id.in_(application_ids)).all()
    documents_by_id = {row.document_id: row for row in documents}
    bank_rows = (db.query(BankCashflowAssessment)
        .filter(BankCashflowAssessment.application_id.in_(application_ids),
                BankCashflowAssessment.user_id == session.user_id)
        .order_by(BankCashflowAssessment.created_at.desc()).all())
    assessments = []
    monthly_by_period = {}
    for row in bank_rows:
        payload = _payload(row)
        finding_by_id = {item.get("document_id"): item for item in (payload.get("document_findings") or [])}
        attached_documents = []
        for document_id in row.evidence_document_ids or []:
            doc = documents_by_id.get(int(document_id))
            if doc is None:
                continue
            finding = finding_by_id.get(doc.document_id, {})
            attached_documents.append({"document_id": doc.document_id, "file_name": doc.file_name,
                "uploaded_at": doc.upload_timestamp.isoformat() if doc.upload_timestamp else None,
                "statement_period": finding.get("statement_period"), "page_count": finding.get("page_count")})
        item = {"assessment_id": row.assessment_id, "application_id": row.application_id,
            "assessment_type": row.assessment_type, "model_version": row.model_version,
            "model_name": payload.get("model_name"),
            "status": row.assessment_status, "score": row.score,
            "currency": payload.get("currency"),
            "assessment_timestamp": payload.get("assessment_timestamp"),
            "observed_months": payload.get("observed_months", []),
            "months_observed": payload.get("months_observed", 0),
            "transaction_count": payload.get("transaction_count", 0),
            "monthly": payload.get("monthly", []), "financial_metrics": payload.get("financial_metrics", {}),
            "recommendations": payload.get("recommendations", []), "documents": attached_documents,
            "fraud_findings": payload.get("fraud_findings"),
            "feature_values": payload.get("feature_values", {}),
            "feature_contributions": payload.get("feature_contributions", []),
            "methodology": payload.get("methodology", {}),
            "evidence": payload.get("evidence", {})}
        assessments.append(item)
        timestamp = item["assessment_timestamp"] or ""
        if row.score is None:
            continue
        balance_by_month = {trend.get('month'):trend.get('average_balance')
            for trend in (payload.get('monthly_balance_trend') or [])}
        for month in item["monthly"]:
            previous = monthly_by_period.get(month["month"])
            if previous is None or timestamp > previous["assessment_timestamp"]:
                monthly_score = month.get("observed_pattern_score")
                pattern_count = month.get("available_pattern_count")
                if "observed_pattern_score" not in month:
                    recalculated = score_observed_month(month.get('income_total') or 0,
                        month.get('expense_total') or 0,
                        month.get('average_balance', balance_by_month.get(month['month'])))
                    monthly_score = recalculated['score']
                    pattern_count = recalculated['available_pattern_count']
                monthly_by_period[month["month"]] = {"month": month["month"],
                    "score": monthly_score,
                    "available_pattern_count": pattern_count,
                    "transaction_count": month.get("credit_count", 0) + month.get("debit_count", 0),
                    "income_total": month.get("income_total"), "expense_total": month.get("expense_total"),
                    "net_flow": month.get("net_flow"), "average_balance": month.get("average_balance"),
                    "assessment_id": row.assessment_id, "assessment_timestamp": timestamp}

    credit_rows = (db.query(ExperimentalAssessment)
        .filter(ExperimentalAssessment.application_id.in_(application_ids),
                ExperimentalAssessment.user_id == session.user_id)
        .order_by(ExperimentalAssessment.created_at.desc()).all())
    for row in credit_rows:
        assessments.append({"assessment_id": row.assessment_id, "application_id": row.application_id,
            "assessment_type": "CREDIT_ACCOUNT_EXPERIMENTAL", "model_version": row.model_version,
            "status": row.assessment_status, "score": float(row.score) if row.score is not None else None,
            "assessment_timestamp": row.created_at.replace(tzinfo=timezone.utc).isoformat(),
            "observed_months": [row.prediction_cutoff_month], "months_observed": 1,
            "transaction_count": None, "monthly": [], "financial_metrics": {},
            "recommendations": row.recommendations or [], "documents": []})
    legacy_rows = (db.query(RiskScore)
        .filter(RiskScore.application_id.in_(application_ids))
        .order_by(RiskScore.generated_at.desc()).all())
    for row in legacy_rows:
        assessments.append({"assessment_id": str(row.score_id), "application_id": row.application_id,
            "assessment_type": "LEGACY_CREDIT_ASSESSMENT", "model_version": row.model_version,
            "status": row.score_status, "score": row.credit_score,
            "assessment_timestamp": row.generated_at.replace(tzinfo=timezone.utc).isoformat() if row.generated_at else None,
            "observed_months": [], "months_observed": None, "transaction_count": None,
            "monthly": [], "financial_metrics": {}, "recommendations": [], "documents": []})
    assessments.sort(key=lambda item: item.get("assessment_timestamp") or "", reverse=True)
    check_events = (db.query(AuditEvent)
        .filter(AuditEvent.application_id.in_(application_ids),
                AuditEvent.action == 'bank_cashflow_assessment_checked')
        .order_by(AuditEvent.event_timestamp.desc()).limit(100).all())
    events_by_assessment = {}
    activity = []
    for event in check_events:
        details = event.details or {}
        assessment_id = details.get('assessment_id')
        checked_at = event.event_timestamp.replace(tzinfo=timezone.utc).isoformat()
        activity.append({'assessment_id':assessment_id,'application_id':event.application_id,
            'checked_at':checked_at,'status':event.status,
            'source_document_count':details.get('source_document_count',0),
            'score_generated':details.get('score_generated',False)})
        events_by_assessment.setdefault(assessment_id, []).append(checked_at)
    for item in assessments:
        item['checked_at'] = events_by_assessment.get(item['assessment_id'], [item.get('assessment_timestamp')])
    return {"application_id": application.application_id, "assessments": assessments,
        "monthly_scores": sorted(monthly_by_period.values(), key=lambda item: item["month"]),
        "activity": activity, "assessment_count": len(assessments)}


@router.post("/{assessment_id}/what-if")
def bank_cashflow_what_if(assessment_id: str, scenario: ScenarioRequest,
        session_id: str = Header(...), db: Session = Depends(get_db)):
    session, app = _session_owner(session_id, db)
    row = db.query(BankCashflowAssessment).filter_by(assessment_id=assessment_id,
        application_id=app.application_id, user_id=session.user_id).first()
    if row is None: raise HTTPException(404, "Bank cash-flow assessment not found")
    if row.score is None: raise HTTPException(409, "What-if scenarios require a scored baseline assessment")
    try:
        simulate = simulate_cashflow_snapshot if row.model_version == SNAPSHOT_VERSION else simulate_bank_health
        return simulate(_payload(row), {k:v for k,v in scenario.dict(exclude_none=True).items()})
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.get("/{assessment_id}")
def bank_cashflow_by_id(assessment_id: str, session_id: str = Header(...), db: Session = Depends(get_db)):
    session, app = _session_owner(session_id, db)
    row = db.query(BankCashflowAssessment).filter_by(assessment_id=assessment_id,
        application_id=app.application_id, user_id=session.user_id).first()
    if row is None: raise HTTPException(404, "Bank cash-flow assessment not found")
    return _payload(row)


@router.get("/{assessment_id}/report.pdf")
def bank_cashflow_pdf(assessment_id: str, session_id: str = Header(...), db: Session = Depends(get_db)):
    session, app = _session_owner(session_id, db)
    row = db.query(BankCashflowAssessment).filter_by(assessment_id=assessment_id,
        application_id=app.application_id, user_id=session.user_id).first()
    if row is None: raise HTTPException(404, "Bank cash-flow assessment not found")
    p = _payload(row)
    title = 'PRISM | Cash-flow snapshot score' if row.model_version == SNAPSHOT_VERSION else 'PRISM | Experimental Bank Financial Health Index'
    lines = [title, f"Assessment: {row.assessment_id}",
        f"Application: {row.application_id}", f"Model version: {row.model_version}",
        f"Status: {row.assessment_status}", f"Index score: {row.score if row.score is not None else 'Not scored'}",
        "Probability of default: Not produced", "Risk tier: Not produced", "Decision use: Not for credit decision",
        f"Currency: {p.get('currency') or 'Unconfirmed'}; months observed: {p.get('months_observed', 0)}; transactions: {p.get('transaction_count', 0)}", "",
        "EVIDENCE GAPS", *(p.get("evidence_gaps", []) or ["None recorded"]), "",
        "FINANCIAL METRICS"]
    if p.get('coverage'):
        lines[0:0] = [f"History coverage: {p['coverage']['history_depth']}; uploaded statement rows only",
                      f"Unknown factors: {', '.join(p['coverage']['unknown_factors']) or 'None'}"]
    lines.extend(f"{key.replace('_', ' ')}: {value}" for key,value in (p.get("financial_metrics") or {}).items())
    lines.extend(["", "MONTHLY CASH FLOW"])
    for month in p.get("monthly", []):
        lines.append(f"{month['month']}: income {month['income_total']}; expenses {month['expense_total']}; net {month['net_flow']}")
    lines.extend(["", "FEATURE CONTRIBUTIONS"])
    for item in p.get("feature_contributions", []):
        lines.append(f"{item['feature']}: value {item['value']}; {item['score_contribution']} points; {item['direction']}")
    lines.extend(["", "GUIDANCE"] + (p.get("recommendations") or []))
    lines.extend(["", "This experimental analytical index is not a validated credit score, bureau score, or PD.",
        "No RBI certification, CIBIL equivalence, or production lending readiness is claimed."])
    doc = fitz.open()
    for offset in range(0, len(lines), 46):
        page = doc.new_page(width=595, height=842)
        page.insert_textbox(fitz.Rect(48, 48, 545, 790), "\n".join(lines[offset:offset+46]), fontsize=10, lineheight=1.3)
    body = doc.tobytes(); doc.close()
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="PRISM-bank-health-{row.assessment_id}.pdf"'})
