import pandas as pd

from features.loan_obligations import RULE_VERSION, review_loan_obligations


def tx(day, amount, narration, direction="DR", doc="701", page=1, line=1, **extra):
    return {"date": day, "amount": amount, "narration": narration, "type": direction,
            "source_document_id": doc, "source_page": page, "source_line": line, **extra}


def test_two_stable_descriptions_overlapping_are_review_signal_not_confirmed_loans():
    rows = [tx(f"2026-{month:02d}-05", 9800, "NACH ALPHA FINANCE LOAN EMI", page=month, line=1)
            for month in (7, 8, 9)]
    rows += [tx(f"2026-{month:02d}-12", 12400, "BETA CREDIT LOAN REPAYMENT", page=month, line=2)
             for month in (7, 8, 9)]
    result = review_loan_obligations(pd.DataFrame(rows), observed_months=["2026-07", "2026-08", "2026-09"], extraction_quality=.95)
    assert result["rule_version"] == RULE_VERSION
    assert result["status"] == "POSSIBLE_OVERLAPPING_REPAYMENT_STREAMS"
    assert result["confirmed_loan_stacking"] is False
    assert result["calibrated_confidence"] is None
    assert len(result["candidate_payment_streams"]) == 2
    assert len(result["overlapping_months"]) == 3
    assert all(item["source_transaction_ids"] for item in result["candidate_payment_streams"])


def test_repeated_installments_for_same_description_remain_one_stream():
    rows = [tx(f"2026-{month:02d}-05", 9800, "NACH ALPHA FINANCE LOAN EMI", page=month)
            for month in (7, 8, 9)]
    result = review_loan_obligations(rows, extraction_quality=.95)
    assert result["status"] == "SINGLE_RECURRING_PAYMENT_STREAM_OBSERVED"
    assert len(result["candidate_payment_streams"]) == 1
    assert result["overlapping_months"] == {}


def test_duplicates_reversals_transfers_and_card_debits_are_excluded():
    rows = [
        tx("2026-07-05", 9800, "ALPHA FINANCE LOAN EMI", page=1, line=1),
        tx("2026-07-05", 9800, "ALPHA FINANCE LOAN EMI", page=1, line=1),
        tx("2026-08-05", 9800, "ALPHA FINANCE LOAN EMI", page=1, line=2),
        tx("2026-08-06", 9800, "ALPHA FINANCE LOAN EMI REVERSAL", direction="CR", line=3),
        tx("2026-09-05", 9800, "ALPHA FINANCE LOAN EMI", page=1, line=4),
        tx("2026-08-08", 12000, "OWN ACCOUNT INTERNAL TRANSFER LOAN EMI", line=5),
        tx("2026-08-09", 4000, "CREDIT CARD BILL PAYMENT EMI", line=6),
    ]
    result = review_loan_obligations(rows, extraction_quality=.95)
    counts = result["exclusions"]
    assert counts["duplicate_rows"] == 1
    assert counts["reversals_or_refunds"] == 2
    assert counts["internal_transfers"] == 1
    assert counts["credit_card_payments"] == 1
    assert len(result["excluded_transaction_ids"]["duplicate_rows"]) == 1
    assert len(result["excluded_transaction_ids"]["internal_transfers"]) == 1
    assert len(result["excluded_transaction_ids"]["credit_card_payments"]) == 1
    assert len(result["candidate_payment_streams"]) == 1
    assert len(result["candidate_payment_streams"][0]["source_transaction_ids"]) == 2


def test_keyword_only_and_single_month_debit_are_insufficient():
    result = review_loan_obligations([
        tx("2026-08-05", 9800, "EMI"),
        tx("2026-08-08", 4000, "LOAN REPAYMENT", page=2),
    ], observed_months=["2026-07", "2026-08", "2026-09"])
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["candidate_payment_streams"] == []
    assert result["data_coverage"]["missing_months"] == ["2026-07", "2026-09"]
    assert result["exclusions"]["unlinked_loan_like_debits"] == 2


def test_invalid_rows_do_not_create_evidence_or_mutate_input():
    source = [tx("not-a-date", 200, "LOAN EMI ALPHA"), tx("2026-08-01", "bad", "LOAN EMI BETA")]
    before = [dict(row) for row in source]
    result = review_loan_obligations(source)
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["data_coverage"]["transactions_reviewed"] == 0
    assert source == before


def test_overlap_with_missing_month_or_low_extraction_quality_stays_insufficient():
    rows = [tx(f"2026-{month:02d}-05", 9800, "ALPHA FINANCE LOAN EMI", page=month)
            for month in (7, 9)]
    rows += [tx(f"2026-{month:02d}-12", 12000, "BETA CREDIT LOAN REPAYMENT", page=month, line=2)
             for month in (7, 9)]
    result = review_loan_obligations(rows, observed_months=["2026-07", "2026-08", "2026-09"], extraction_quality=.95)
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["data_coverage"]["sufficiency_gaps"] == ["GAPS_IN_OBSERVED_MONTH_COVERAGE"]
    result = review_loan_obligations(rows, extraction_quality=.6)
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert "EXTRACTION_QUALITY_BELOW_80_PERCENT_OR_UNKNOWN" in result["data_coverage"]["sufficiency_gaps"]
