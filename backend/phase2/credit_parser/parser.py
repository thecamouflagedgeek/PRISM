"""Structured and controlled-text statement field extraction. Not a PDF/OCR parser."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Mapping
from .models import ParseState, FieldIssue, ParsedStatement, ParsedRepaymentRecord
from .field_mapping import TEXT_LABELS
from .provenance_builder import provenance, source
from ..credit_evidence.models import (EvidenceValue, ValueState, RepaymentStatus,
    RepaymentStatusKind, ProductType, SourceType, SourceRole)

# Deliberately constrained ISO 4217 allowlist for controlled fixtures; never guess a symbol's currency.
ISO_CURRENCIES={"USD","INR","EUR","GBP","CAD","AUD","JPY","CHF","SGD"}

def normalize_month(value) -> str:
    if isinstance(value,(date,datetime)): return value.strftime("%Y-%m")
    text=str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}",text):
        y,m=map(int,text.split("-"));
        if not 1<=m<=12: raise ValueError("month out of range")
        return text
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y",
                "%d-%b-%Y", "%d %b %Y", "%b %Y", "%B %Y", "%m/%Y", "%m-%Y"):
        try: return datetime.strptime(text, fmt).strftime("%Y-%m")
        except ValueError: pass
    raise ValueError(f"unsupported statement month: {value}")

def normalize_currency(value) -> str:
    text=str(value).strip().upper().replace(".", "")
    return {"₹":"INR", "RS":"INR", "INR":"INR", "$":"USD", "USD":"USD",
            "€":"EUR", "EUR":"EUR", "£":"GBP", "GBP":"GBP", "¥":"JPY", "JPY":"JPY"}.get(text,text)

def normalize_provider(value: str) -> tuple[str,str]:
    display=" ".join(str(value).strip().split())
    key=re.sub(r"[^a-z0-9]", "", display.casefold())
    if not key: raise ValueError("provider is required")
    return display,key

def normalize_amount(value) -> Decimal:
    if isinstance(value,Decimal): out=value
    else:
        text=str(value).strip().replace(",","").replace(" ","")
        neg=text.startswith("(") and text.endswith(")")
        if neg: text=text[1:-1]
        text=text.replace("₹","").replace("$","").replace("€","").replace("£","")
        try: out=Decimal(text)
        except InvalidOperation as e: raise ValueError(f"invalid numeric amount: {value}") from e
        if neg: out=-out
    if not out.is_finite(): raise ValueError("numeric amount must be finite")
    return out

def _metadata(payload, source_type):
    m=payload.get("source_metadata") or {}
    required=("source_document_id","extraction_method","extraction_confidence","account_link_confidence","authenticated")
    missing=[key for key in required if key not in m or m[key] is None]
    if missing: raise ValueError("required source metadata absent: "+", ".join(missing))
    doc=str(m.get("source_document_id","")).strip()
    if not doc: raise ValueError("source_metadata.source_document_id is required")
    method=str(m.get("extraction_method"))
    confidence=float(m.get("extraction_confidence"))
    link=float(m.get("account_link_confidence"))
    if not isinstance(m.get("authenticated"),bool): raise ValueError("source_metadata.authenticated must be boolean")
    authenticated=m["authenticated"]
    if not 0<=confidence<=1 or not 0<=link<=1: raise ValueError("confidence must be between 0 and 1")
    return m,doc,method,confidence,link,authenticated

def _status(raw, *, doc, source_type, method, confidence, record_id):
    if raw is None: return RepaymentStatus(ValueState.MISSING),False
    try:
        code=raw.get("status") if isinstance(raw,Mapping) else raw
        status=RepaymentStatusKind(str(code).strip().upper())
        level=(raw.get("delinquency_severity",raw.get("delinquency_level")) if isinstance(raw,Mapping) else None)
        if level is not None: level=int(level)
        src_code=str(raw.get("source_code",code)) if isinstance(raw,Mapping) else str(code)
        prov=provenance(document_id=doc,source_type=source_type,field="repayment_status",original=raw,normalized={"status":status.value,"delinquency_level":level},method=method,confidence=confidence,record_id=record_id)
        return RepaymentStatus(ValueState.PRESENT,status,level,source_code=src_code,provenance=(prov,)),False
    except (ValueError,TypeError,AttributeError) as e:
        return RepaymentStatus(ValueState.INVALID,source_code=str(raw)),True

def _parse_statement(payload: Mapping, *, text_format=False) -> ParsedStatement:
    issues=[]
    def val(name): return payload.get(name)
    try: meta,doc,method,conf,link,auth=_metadata(payload,SourceType.CREDIT_CARD_STATEMENT)
    except (ValueError,TypeError) as e:
        issue=FieldIssue("source_metadata","INVALID_METADATA",str(e))
        return ParsedStatement(ParseState.INVALID,None,None,None,None,None,None,None,EvidenceValue(ValueState.MISSING),EvidenceValue(ValueState.MISSING),RepaymentStatus(ValueState.MISSING),None,(issue,))
    account=str(val("account_reference") or "").strip() or None
    raw_provider=val("provider")
    try: provider,key=normalize_provider(raw_provider) if raw_provider else (None,None)
    except ValueError: provider,key=None,None
    if not account: issues.append(FieldIssue("account_reference","MISSING_REQUIRED","account reference absent"))
    if not provider: issues.append(FieldIssue("provider","MISSING_REQUIRED","provider absent"))
    masked=str(val("masked_account_number") or "").strip() or None
    if masked and re.fullmatch(r"\d{12,19}",masked):
        issues.append(FieldIssue("masked_account_number","SENSITIVE_ID_REJECTED","full account number is prohibited")); masked=None
    if not masked: issues.append(FieldIssue("masked_account_number","MISSING_REQUIRED","masked identifier absent"))
    currency=normalize_currency(val("currency") or "")
    if currency not in ISO_CURRENCIES:
        issues.append(FieldIssue("currency","INVALID_CURRENCY","currency not in controlled ISO 4217 allowlist")); currency=None
    month=None
    try:
        raw_month=val("statement_month")
        if raw_month is None: raise ValueError("missing statement month")
        month=normalize_month(raw_month)
    except ValueError as e: issues.append(FieldIssue("statement_month","INVALID_MONTH",str(e)))
    try: product=ProductType(str(val("product_type") or "").strip().upper())
    except ValueError: product=None; issues.append(FieldIssue("product_type","UNSUPPORTED_PRODUCT","product type is absent or unsupported"))
    record_id=str((meta or {}).get("page_or_record_id") or month or doc)
    field_locations=meta.get("field_provenance") or {}
    def field_record(field):
        location=field_locations.get(field)
        if isinstance(location,Mapping) and location.get("page") and location.get("line"):
            return f"page:{location['page']}:line:{location['line']}"
        return record_id
    def amount(field):
        raw=val(field)
        if raw is None:
            issues.append(FieldIssue(field,"MISSING_REQUIRED",f"{field} unavailable")); return EvidenceValue(ValueState.MISSING)
        try:
            normalized=normalize_amount(raw)
            if field=="payment_amount" and normalized<0: raise ValueError("negative payment must be resolved as a confirmed reversal before normalization")
            p=provenance(document_id=doc,source_type=SourceType.CREDIT_CARD_STATEMENT,field=field,original=raw,normalized=str(normalized),method=method,confidence=conf,record_id=field_record(field),transform="Decimal currency amount")
            return EvidenceValue(ValueState.PRESENT,normalized,currency,(p,))
        except (ValueError,TypeError) as e:
            issues.append(FieldIssue(field,"INVALID_NUMERIC",str(e))); return EvidenceValue(ValueState.INVALID,reason=str(e))
    balance=amount("statement_balance"); payment=amount("payment_amount")
    repayment,status_invalid=_status(val("repayment_status"),doc=doc,source_type=SourceType.CREDIT_CARD_STATEMENT,method=method,confidence=conf,record_id=field_record("repayment_status"))
    if status_invalid: issues.append(FieldIssue("repayment_status","INVALID_STATUS","explicit status/severity invalid"))
    if repayment.state is ValueState.MISSING: issues.append(FieldIssue("repayment_status","MISSING_STATUS","statement does not explicitly state repayment status"))
    src=source(document_id=doc,source_type=SourceType.CREDIT_CARD_STATEMENT,role=SourceRole.PRIMARY_ACCOUNT_SOURCE,account_reference=account or "unresolved",confidence=link,authenticated=auth,record_ids=(record_id,))
    fatal=any(i.code in {"INVALID_CURRENCY","INVALID_MONTH","INVALID_NUMERIC","INVALID_STATUS","INVALID_METADATA","SENSITIVE_ID_REJECTED"} for i in issues)
    complete=not issues
    unsupported=any(i.code=="UNSUPPORTED_PRODUCT" for i in issues)
    state=ParseState.INVALID if fatal else ParseState.UNSUPPORTED if unsupported else ParseState.PARSED if complete else ParseState.PARTIALLY_PARSED
    return ParsedStatement(state,account,product,provider,key,masked,currency,month,balance,payment,repayment,src,tuple(issues))

def parse_structured_statement(payload: Mapping) -> ParsedStatement:
    """Parse canonical extracted fields; do not infer values absent from source."""
    if not isinstance(payload,Mapping): raise TypeError("structured statement must be a mapping")
    return _parse_statement(payload)

def parse_controlled_text_statement(text: str, *, source_metadata: Mapping) -> ParsedStatement:
    """Parse only the explicitly documented EXPERIMENTAL_FIXTURE_FORMAT label/value syntax."""
    fields={"source_metadata":dict(source_metadata)}
    for line in text.splitlines():
        if ":" not in line: continue
        label,value=line.split(":",1); key=label.strip().upper()
        mapped=TEXT_LABELS.get(key)
        if mapped: fields[mapped]=value.strip()
    if fields.get("status"):
        fields["repayment_status"]={"status":fields.pop("status"),"delinquency_severity":fields.pop("delinquency_severity",None)}
    fields.setdefault("product_type","CREDIT_CARD")
    return _parse_statement(fields,text_format=True)

def parse_repayment_history(payload: Mapping) -> ParsedRepaymentRecord:
    issues=[]
    try: meta,doc,method,conf,link,auth=_metadata(payload,SourceType.BUREAU_HISTORY)
    except (ValueError,TypeError) as e:
        return ParsedRepaymentRecord(ParseState.INVALID,None,None,None,None,None,RepaymentStatus(ValueState.MISSING),None,(FieldIssue("source_metadata","INVALID_METADATA",str(e)),))
    account=str(payload.get("account_reference") or "").strip() or None
    provider,key=normalize_provider(payload.get("provider","")) if payload.get("provider") else (None,None)
    try: product=ProductType(str(payload.get("product_type","CREDIT_CARD")).upper())
    except ValueError: product=None; issues.append(FieldIssue("product_type","UNSUPPORTED_PRODUCT","unsupported product"))
    try: month=normalize_month(payload.get("month"))
    except (ValueError,TypeError): month=None; issues.append(FieldIssue("month","INVALID_MONTH","invalid repayment month"))
    raw={"status":payload.get("repayment_status"),"delinquency_severity":payload.get("delinquency_severity"),"source_code":payload.get("source_code",payload.get("repayment_status"))}
    repayment,bad=_status(raw if raw["status"] is not None else None,doc=doc,source_type=SourceType.BUREAU_HISTORY,method=method,confidence=conf,record_id=month or doc)
    if bad: issues.append(FieldIssue("repayment_status","INVALID_STATUS","explicit repayment status/severity invalid"))
    if repayment.state is ValueState.MISSING: issues.append(FieldIssue("repayment_status","MISSING_STATUS","status absent"))
    src=source(document_id=doc,source_type=SourceType.BUREAU_HISTORY,role=SourceRole.SUPPORTING_SOURCE,account_reference=account or "unresolved",confidence=link,authenticated=auth,record_ids=(month or doc,))
    state=ParseState.INVALID if any(i.code in {"INVALID_MONTH","INVALID_STATUS"} for i in issues) else ParseState.PARSED if not issues and account and provider and product and month else ParseState.PARTIALLY_PARSED
    return ParsedRepaymentRecord(state,account,product,provider,key,month,repayment,src,tuple(issues))
