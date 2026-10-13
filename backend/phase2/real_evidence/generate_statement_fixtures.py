"""Generate reproducible, clearly synthetic card-statement PDF/OCR fixtures."""
from __future__ import annotations

import argparse
import calendar
from datetime import datetime, timezone
import json
from pathlib import Path

import fitz

from phase2.credit_parser.normalizer import run_equivalence_path
from phase2.credit_evidence.models import Consent, ConsentState
from phase2.shadow_scorecard.artifacts import load_scorecard
from phase2.shadow_scorecard.scorer import score_validated_result


OUT = Path(__file__).resolve().parents[1] / "outputs" / "synthetic_statement_fixtures"
PROFILES = {
    "consistent": {"mask": "****1001", "balances": [1200, 1300, 1100, 1400, 1250, 1350],
        "ratios": [.75, .80, .85, .70, .90, .80], "levels": [0, 0, 0, 0, 0, 0]},
    "moderate": {"mask": "****2002", "balances": [2400, 2650, 2500, 2900, 2750, 3100],
        "ratios": [.50, .35, .80, .45, .30, .60], "levels": [0, 1, 0, 0, 2, 1]},
    "repeated": {"mask": "****3003", "balances": [8400, 9100, 9800, 10200, 11100, 12000],
        "ratios": [.20, .15, .10, .18, .08, .12], "levels": [3, 4, 5, 4, 6, 9]},
}


def months_before(cutoff: str):
    year, month = map(int, cutoff.split("-"))
    out = []
    for offset in range(6, 0, -1):
        serial = year * 12 + month - 1 - offset
        y, m = divmod(serial, 12)
        out.append(f"{y:04d}-{m + 1:02d}")
    return out


def main(cutoff: str):
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    consent = Consent(ConsentState.GRANTED, frozenset({"CREDIT_CARD_STATEMENTS"}),
        granted_at=datetime(2026, 1, 1, tzinfo=timezone.utc), version="synthetic-fixture-v1")
    artifact = load_scorecard()
    for profile_name, profile in PROFILES.items():
        statements, files = [], []
        account = f"SYNTHETIC-{profile_name.upper()}-CARD"
        for index, month in enumerate(months_before(cutoff)):
            balance = profile["balances"][index]
            payment = round(balance * profile["ratios"][index], 2)
            level = profile["levels"][index]
            year, month_no = map(int, month.split("-"))
            last_day = calendar.monthrange(year, month_no)[1]
            due_day = min(20, last_day)
            status = "DELINQUENT" if level > 0 else "CURRENT"
            doc_id = f"SYNTH-{profile_name}-{month}"
            metadata = {"source_document_id": doc_id, "extraction_method": "synthetic_labeled_pdf",
                "extraction_confidence": 1.0, "account_link_confidence": 1.0,
                "authenticated": True, "page_or_record_id": "page:1"}
            statements.append({"account_reference": account, "product_type": "CREDIT_CARD",
                "provider": "PRISM Synthetic Issuer", "masked_account_number": profile["mask"],
                "currency": "INR", "statement_month": month, "statement_balance": str(balance),
                "payment_amount": str(payment), "repayment_status": {"status": status,
                    "delinquency_severity": level, "source_code": f"SYNTHETIC_LEVEL_{level}"},
                "source_metadata": metadata})
            text = "\n".join([
                "PRISM SYNTHETIC CREDIT CARD STATEMENT — NOT A REAL ACCOUNT",
                f"Provider: PRISM Synthetic Issuer", f"Statement Date: {year:04d}-{month_no:02d}-{last_day:02d}",
                f"Statement Period: {month}-01 through {month}-{last_day:02d}",
                f"Statement Month: {month}", f"Account Reference: {account}",
                f"Account: {profile['mask']}", "Product: CREDIT_CARD", "Currency: INR",
                f"Statement Balance: {balance:.2f}", f"Total Amount Due: {balance:.2f}",
                f"Minimum Amount Due: {balance * .05:.2f}",
                f"Payment Applied to Statement: {payment:.2f}",
                f"Payment Date: {year:04d}-{month_no:02d}-{min(last_day, 18):02d}",
                f"Payment Due Date: {year:04d}-{month_no:02d}-{due_day:02d}",
                f"Repayment Status: {status}", f"Delinquency Level: {level}",
                "All figures and identities are synthetic test data.",
            ])
            pdf_path = OUT / f"{profile_name}_{month}.pdf"
            document = fitz.open()
            page = document.new_page(width=595, height=842)
            page.insert_textbox(fitz.Rect(44, 48, 550, 800), text, fontsize=11, lineheight=1.35)
            document.save(pdf_path)
            document.close()
            files.append(str(pdf_path))
            if profile_name == "repeated" and index == 5:
                source = fitz.open(pdf_path)
                pix = source[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image_path = OUT / f"{profile_name}_{month}_scanned.png"
                pix.save(image_path)
                scan = fitz.open()
                page = scan.new_page(width=595, height=842)
                page.insert_image(page.rect, filename=str(image_path))
                scanned_pdf = OUT / f"{profile_name}_{month}_scanned.pdf"
                scan.save(scanned_pdf)
                scan.close(); source.close()
                files.extend([str(image_path), str(scanned_pdf)])
        assembly = run_equivalence_path(statements, (), consent=consent,
            prediction_cutoff_month=cutoff, borrower_reference=f"synthetic-{profile_name}",
            at=datetime(2026, 10, 1, tzinfo=timezone.utc))
        if not assembly.eligibility.eligible_for_phase2b6_scorecard:
            raise RuntimeError(f"Synthetic ground truth failed Phase 2E validation: {assembly.eligibility.blocking_reasons}")
        scored = score_validated_result(assembly, artifact=artifact)
        rows.append({"profile": profile_name, "synthetic_only": True, "prediction_cutoff_month": cutoff,
            "files": files, "statement_ground_truth": [{k: v for k, v in row.items() if k != "source_metadata"} for row in statements],
            "feature_vector": {k: str(assembly.features.values[k]) for k in assembly.features.values},
            "feature_order": list(assembly.features.values), "woe_bins": scored["bin_assignments"],
            "woe_values": scored["woe_values"], "pd": scored["pd"], "uncapped_score": scored["score"],
            "reason_codes": [{"code": r["code"], "contribution": r["contribution"]} for r in scored["reason_codes"]],
            "artifact_sha256": artifact["artifact_sha256"],
            "limitations": ["SYNTHETIC_TEST_DATA", "NOT_FOR_CREDIT_DECISION"]})
    target = OUT / "ground_truth.json"
    target.write_text(json.dumps({"synthetic_fixture_version": "1", "profiles": rows}, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUT), "profile_count": len(rows),
        "pdf_count": len(list(OUT.glob("*.pdf"))), "scanned_png_count": len(list(OUT.glob("*_scanned.png"))),
        "ground_truth": str(target)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff-month", default=datetime.now().strftime("%Y-%m"))
    main(parser.parse_args().cutoff_month)
