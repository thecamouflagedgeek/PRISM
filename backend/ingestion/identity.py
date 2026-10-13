"""Conservative, transient name comparison for documents in one assessment."""
import re
import unicodedata


IDENTITY_LABEL = re.compile(
    r"^\s*(account\s+holder(?:\s+name)?|name\s+of\s+account\s+holder|account\s+name|"
    r"customer\s+name|consumer\s+name|billing\s+name|employee\s+name|"
    r"applicant\s+name|payee\s+name|full\s+name|name)\s*[:\-]?\s*(.*?)\s*$", re.I)
NON_NAME = re.compile(r"\b(?:account|savings|current|salary|customer|employee|consumer|bill|statement|branch|address|"
                      r"ifsc|micr|bank|inr|male|female|date|amount|department|designation)\b", re.I)
TITLE = {"mr", "mrs", "ms", "miss", "dr", "shri", "smt", "kumari"}
NEXT_FIELD = re.compile(r"^(?:address|branch|account no|account number|ifsc|micr|phone|mobile|email|date|period|"
                         r"department|designation|gross pay|total deductions|net salary|amount|inr|pan|"
                         r"consumer number|service number|bill date|billing period)\b", re.I)


def normalize_person_name(value: str | None) -> str | None:
    if not value:
        return None
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"\b(?:mr|mrs|ms|miss|dr|shri|smt|kumari)\.?\b", " ", value)
    value = re.sub(r"\b(?:fictional|synthetic)\b", " ", value)
    value = re.sub(r"[^a-z\s'-]", " ", value)
    tokens = [token.strip("-' ") for token in value.split()]
    tokens = [token for token in tokens if token]
    if len(tokens) < 2 or len(tokens) > 6 or NON_NAME.search(" ".join(tokens)):
        return None
    if not all(re.fullmatch(r"[a-z][a-z'-]{0,39}", token) for token in tokens):
        return None
    return " ".join(tokens)


def extract_person_name(text: str) -> str | None:
    """Read only explicit person-name labels; reject conflicting names."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    names = set()
    for index, line in enumerate(lines):
        match = IDENTITY_LABEL.match(line)
        if not match:
            continue
        candidate = normalize_person_name(match.group(2))
        if candidate is None and not match.group(2):
            for following in lines[index + 1:index + 3]:
                if not following or IDENTITY_LABEL.match(following):
                    continue
                if NEXT_FIELD.match(following):
                    break
                candidate = normalize_person_name(following)
                if candidate:
                    break
        if candidate:
            names.add(candidate)
    return next(iter(names)) if len(names) == 1 else None


def verify_document_identities(bank_metadata: list[dict], supporting_documents: list[dict]) -> dict:
    """Verify all supplied holder names without returning or storing the names."""
    if not supporting_documents:
        return {"status": "NOT_NEEDED", "verified": True}
    records = [(item.get("file_name") or "Bank statement", item.get("holder_name"))
               for item in bank_metadata]
    records.extend((item.get("file_name") or "Supporting document", item.get("_identity_name"))
                   for item in supporting_documents)
    missing = [name for name, identity in records if not identity]
    known = {identity for _, identity in records if identity}
    mismatched = len(known) > 1
    baseline = next((identity for _, identity in records if identity), None)
    return {"status": "MISMATCH" if mismatched else "UNVERIFIED" if missing else "MATCHED",
            "verified": not mismatched and not missing,
            "mismatched_documents": [name for name, identity in records if identity and identity != baseline] if mismatched else [],
            "unverified_documents": missing}
