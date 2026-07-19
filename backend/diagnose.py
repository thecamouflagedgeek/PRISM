"""
diagnose.py
Run from backend/:  python diagnose.py

End-to-end diagnostic: takes REAL bank statement text (no need for a file
path -- pass raw extracted text directly), runs it through the actual
BankExtractor -> BankFeatureEngineer -> risk_scorer WoE transform chain,
with salary/utility documents simulated as MISSING (the real-world scenario
that produced 300 scores).

This confirms or rules out the hypothesis: does a missing document actually
produce WoE = 0.0 for that feature on the CURRENT (restored, original)
live artifacts?
"""

from ingestion.universal_pipeline import BankExtractor
from features.bank_features import BankFeatureEngineer, BankFeatureEngineerError

# --- Paste real bank statement text here (or read from a .txt dump) ---
# Using the Bank of Baroda statement text as a real-world stand-in.
REAL_BANK_TEXT = r"""
BANK OF BARODA Date :15-06-2026 S.V.ROAD ANDHERI WEST Time : 16:58:34
01-12-25 B/F 5,91,519.05Cr
02-12-25 IMPS/P2A/53361 1,00,000.00 4,91,519.05Cr
IMPS/P2A/533614021368/XXXXXXXXXX0426/Loantojaiici 08-12-25 IMPS/P2A/53422
1,00,000.00 3,91,519.05Cr
IMPS/P2A/534223684620/XXXXXXXXXX0426/Giventojai 08-12-25 IMPS/P2A/53422
1,00,000.00 2,91,519.05Cr
09-12-25 IMPS/P2A/53431 2,00,000.00 91,519.05Cr
22-12-25 IMPS/P2A/53561 25,000.00 66,519.05Cr
29-12-25 IMPS/P2A/53630 15,000.00 51,519.05Cr
29-12-25 IMPS/P2A/53630 16,000.00 35,519.05Cr
30-12-25 NEFT-BARBT2536 10,000.00 25,519.05Cr
13-01-26 EBANK:WIB/1490 1,000.00 24,519.05Cr
06-02-26 :Int.Pd:01-11-26056 4,191.00 28,710.05Cr
09-02-26 RTGS-YESBR5202 13,37,745.62 13,66,455.67Cr
09-02-26 EBANK:SELF/149 13,37,745.00 28,710.67Cr
"""

# --- Step 1: run raw text through the REAL extractor (bypassing PDF I/O) ---
print("=== STEP 1: BankExtractor ===")
bank_result = BankExtractor().extract(REAL_BANK_TEXT)
print("doc_type:", bank_result.doc_type)
print("confidence:", bank_result.confidence)
print("entities_found:", bank_result.entities_found)
print("missing_entities:", bank_result.missing_entities)
print("diagnostics:", bank_result.diagnostics)
print("\nExtracted transaction rows:")
print(bank_result.data)

if bank_result.data is None or bank_result.data.empty:
    raise SystemExit("Extractor produced no transaction rows -- cannot proceed. "
                      "Check REAL_BANK_TEXT formatting / regex matches.")

# --- Step 2: run extracted rows through the REAL feature engineer ---
print("\n=== STEP 2: BankFeatureEngineer ===")
try:
    engineer = BankFeatureEngineer(bank_result.data)
    bank_features = engineer.build_features()
    print("bank_features:", bank_features)
except BankFeatureEngineerError as e:
    print(f"BankFeatureEngineerError: {e}")
    bank_features = None

if bank_features is None:
    raise SystemExit("Feature engineering failed -- cannot proceed to scoring diagnostic.")

# --- Step 3: simulate the real-world scenario -- salary & utility MISSING ---
print("\n=== STEP 3: Simulate missing salary + utility documents ===")
salary_features = None   # applicant did not submit a salary slip
utility_features = None  # applicant did not submit a utility bill

# --- Step 4: run through the ACTUAL scoring engine's feature mapping + WoE ---
print("\n=== STEP 4: risk_scorer feature mapping + WoE transform ===")
from scoring.risk_scorer import _load_artifacts, _map_features, _woe_transform

_load_artifacts()

# _map_features expects bank/salary/utility dicts with specific key names --
# bank_features from BankFeatureEngineer uses "min_balance_l3m" and
# "credit_debit_ratio" / "cashflow_cv" which already match _map_features'
# expected source keys (see _map_features in risk_scorer.py).
feature_dict = _map_features(bank_features, salary_features, utility_features)
X_woe = _woe_transform(feature_dict)

print("\nfeature_dict (raw values, None = missing):")
print(feature_dict)
print("\nX_woe (WoE-transformed):")
print(X_woe)

print("\n=== DIAGNOSIS ===")
for col in ["net_to_gross_ratio", "utility_stability", "cashflow_cv"]:
    val = feature_dict.get(col)
    woe = X_woe[col].iloc[0]
    if val is None and woe == 0.0:
        print(f"  {col:22s} MISSING -> WoE = 0.0  <-- CONFIRMED: zero-signal on missing document")
    elif val is None:
        print(f"  {col:22s} MISSING -> WoE = {woe:.4f}  (non-zero -- Missing bin has real signal)")
    else:
        print(f"  {col:22s} present ({val}) -> WoE = {woe:.4f}")