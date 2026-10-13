import json
from pathlib import Path
import sys
import pytest

BACKEND=Path(__file__).resolve().parents[2]
ROOT=BACKEND.parent
sys.path.insert(0,str(BACKEND/'phase2'/'feature_compatibility'))
from feature_schema_v2 import (  # noqa: E402
    FEATURES, COMPATIBILITY_CLASSES, validate_compatibility, validate_provenance,
    expected_months, normalize_uci_repayment_status, ratio_from_six_months,
    derive_from_monthly_credit_history,
)

OUT=BACKEND/'phase2'/'outputs'/'phase2c'
BASELINE=json.loads((BACKEND/'phase2'/'feature_compatibility'/'protected_hashes_before.json').read_text(encoding='utf-8-sig'))

def fixture_records(doc_type='credit_account_monthly_history'):
    months=expected_months('2005-10',6)
    delays=[0,1,0,2,0,3]
    bills=[100,200,300,400,500,600]
    pays=[0,100,150,200,250,300]
    records=[]
    for i,m in enumerate(months):
        records.append({'statement_month':m,'account_id':'CARD-001','product_type':'credit_card','repayment_delay_months':delays[i],'statement_balance':bills[i],'payment_amount':pays[i],
          'provenance':{'document_id':f'DOC-{i}','document_type':doc_type,'page_or_record_id':f'row-{i}','period_month':m,
            'raw_field_map':{'status':'raw_status','balance':'raw_bill','payment':'raw_payment'},
            'normalized_field_map':{'repayment_delay_months':'status','statement_balance':'balance','payment_amount':'payment'},
            'extraction_method':'structured_fixture','extraction_confidence':1.0}})
    return records

def file_hash(relative_path):
    import hashlib
    return hashlib.sha256((ROOT/relative_path).read_bytes()).hexdigest().upper()

def test_frozen_phase2b6_definitions_loaded_exactly():
    doc=json.loads((OUT/'phase2b6_feature_definitions.json').read_text(encoding='utf-8'))
    assert set(doc['features'])==set(FEATURES)
    assert doc['features']['recent_delinquency_level']['uci_source_columns']==['PAY_0']
    assert doc['features']['months_with_delinquency']['uci_source_columns']==['PAY_0','PAY_2','PAY_3','PAY_4','PAY_5','PAY_6']
    assert 'max(BILL_AMT1..BILL_AMT6, 0)' in doc['features']['payment_to_statement_ratio']['formula']
    assert doc['features']['mean_statement_balance']['formula']=='mean(BILL_AMT1..BILL_AMT6), preserving signed source values.'

def test_semantic_compatibility_enum_is_closed():
    assert set(COMPATIBILITY_CLASSES)=={'DIRECTLY_REPRODUCIBLE','REPRODUCIBLE_WITH_NEW_DOCUMENT_TYPE','STRONG_SEMANTIC_PROXY','WEAK_PROXY','NOT_REPRODUCIBLE'}
    for label in COMPATIBILITY_CLASSES: assert validate_compatibility(label)==label
    with pytest.raises(ValueError): validate_compatibility('CLOSE_ENOUGH')

def test_provenance_requirements_validate_full_lineage():
    validate_provenance(fixture_records()[0])
    with pytest.raises(ValueError,match='PROVENANCE_INCOMPLETE'):
        validate_provenance({'provenance':{'document_type':'credit_card_statement'}})

def test_six_complete_calendar_month_window_precedes_cutoff():
    assert expected_months('2005-10',6)==['2005-04','2005-05','2005-06','2005-07','2005-08','2005-09']

def test_zero_is_valid_observation_and_absence_is_missing():
    result=derive_from_monthly_credit_history(fixture_records(),'2005-10')
    assert result['values']['recent_delinquency_level']==3
    clean=fixture_records()
    for row in clean: row['repayment_delay_months']=0
    assert derive_from_monthly_credit_history(clean,'2005-10')['values']['months_with_delinquency']==0
    missing=derive_from_monthly_credit_history([],'2005-10')
    assert missing['feature_states']['months_with_delinquency']=='MISSING_REQUIRED_EVIDENCE'
    assert missing['values']['months_with_delinquency'] is None

def test_missing_and_not_applicable_are_distinct_and_na_needs_evidence():
    absent=derive_from_monthly_credit_history([],'2005-10','UNKNOWN')
    assert set(absent['feature_states'].values())=={'MISSING_REQUIRED_EVIDENCE'}
    unverified=derive_from_monthly_credit_history([],'2005-10','NO_CREDIT_FACILITY')
    assert set(unverified['feature_states'].values())=={'MISSING_REQUIRED_EVIDENCE'}
    na=derive_from_monthly_credit_history([],'2005-10','NO_CREDIT_FACILITY',{'verified':True,'source_id':'bureau-123'})
    assert set(na['feature_states'].values())=={'NOT_APPLICABLE'}
    assert set(na['values'].values())=={None}

def test_ratio_zero_denominator_is_not_zero():
    result=ratio_from_six_months([0]*6,[0]*6)
    assert result=={'value':None,'feature_state':'INSUFFICIENT_DENOMINATOR'}

def test_ratio_zero_numerator_positive_denominator_is_valid_zero():
    assert ratio_from_six_months([0]*6,[100]*6)=={'value':0.0,'feature_state':'VALID'}

def test_ratio_handles_zero_statement_balance_and_zero_payment():
    assert ratio_from_six_months([0]*6,[0]*6)['feature_state']=='INSUFFICIENT_DENOMINATOR'

def test_ratio_missing_denominator_fails_closed():
    assert ratio_from_six_months([1]*6,[100,100,None,100,100,100])['feature_state']=='MISSING_REQUIRED_EVIDENCE'

def test_ratio_rejects_negative_payment_but_obeys_frozen_negative_balance_rule():
    assert ratio_from_six_months([-1,0,0,0,0,0],[1]*6)['feature_state']=='INVALID_EVIDENCE'
    got=ratio_from_six_months([10,0,0,0,0,0],[-100,100,0,0,0,0])
    assert got['feature_state']=='VALID' and got['value']==0.1

def test_ratio_does_not_clamp_extreme_valid_values():
    got=ratio_from_six_months([1e12,0,0,0,0,0],[1,0,0,0,0,0])
    assert got['value']==1e12

def test_incomplete_history_does_not_make_partial_feature_values():
    rows=fixture_records()[:-1]
    got=derive_from_monthly_credit_history(rows,'2005-10')
    assert got['missing_months']==['2005-09']
    assert set(got['feature_states'].values())=={'MISSING_REQUIRED_EVIDENCE'}
    assert set(got['values'].values())=={None}

def test_future_period_is_rejected():
    rows=fixture_records(); rows[-1]['statement_month']='2005-10'; rows[-1]['provenance']['period_month']='2005-10'
    with pytest.raises(ValueError,match='FUTURE_PERIOD_REJECTED'): derive_from_monthly_credit_history(rows,'2005-10')

def test_mixed_account_history_is_rejected():
    rows=fixture_records(); rows[-1]['account_id']='CARD-OTHER'
    with pytest.raises(ValueError,match='ACCOUNT_OR_PRODUCT_MISMATCH'): derive_from_monthly_credit_history(rows,'2005-10')

def test_invalid_repayment_status_is_rejected():
    for bad in (-3,10,'late'):
        with pytest.raises(ValueError,match='INVALID_REPAYMENT_STATUS'): normalize_uci_repayment_status(bad)
    rows=fixture_records(); rows[0]['repayment_delay_months']=1.5
    with pytest.raises(ValueError,match='INVALID_EVIDENCE_VALUE'): derive_from_monthly_credit_history(rows,'2005-10')

def test_uci_repayment_recode_matches_frozen_model_code():
    assert [normalize_uci_repayment_status(x) for x in (-2,-1,0,1,9)]==[0,0,0,1,9]

def test_unsupported_document_types_are_rejected_not_substituted():
    rows=fixture_records('bank_statement')
    with pytest.raises(ValueError,match='UNSUPPORTED_DOCUMENT_TYPE'): derive_from_monthly_credit_history(rows,'2005-10')

def test_experimental_contract_fixture_is_not_claimed_as_current_parser_equivalence():
    matrix=list(__import__('csv').DictReader((OUT/'feature_compatibility_matrix.csv').open(encoding='utf-8')))
    assert all(r['compatibility']=='REPRODUCIBLE_WITH_NEW_DOCUMENT_TYPE' for r in matrix)
    assert all(r['exact_formula_reproducible_today']=='False' for r in matrix)
    got=derive_from_monthly_credit_history(fixture_records(),'2005-10')
    assert got['values']['months_with_delinquency']==3
    assert got['values']['payment_to_statement_ratio']==1000/2100

def test_bank_utility_salary_semantic_proxies_are_never_input_contracts():
    for doc in ('bank_statement','utility_bill','salary_slip'):
        with pytest.raises(ValueError,match='UNSUPPORTED_DOCUMENT_TYPE'):
            derive_from_monthly_credit_history(fixture_records(doc),'2005-10')

def test_missing_values_never_become_zero_or_woe_zero():
    got=derive_from_monthly_credit_history([],'2005-10')
    assert all(v is None for v in got['values'].values())
    schema=json.loads((OUT/'feature_schema_v2.json').read_text(encoding='utf-8'))
    assert schema['no_missing_to_zero'] is True and schema['no_woe_for_missing'] is True

def test_production_artifact_bundle_hashes_match_pre_audit_snapshot():
    for item in BASELINE:
        if item['scope']=='production_artifact': assert file_hash(item['relative_path'])==item['sha256']

def test_production_model_hash_unchanged():
    item=next(x for x in BASELINE if x['relative_path'].endswith('/lr_model.pkl'))
    assert file_hash(item['relative_path'])==item['sha256']

def test_production_binning_hash_unchanged():
    item=next(x for x in BASELINE if x['relative_path'].endswith('/binning.pkl'))
    assert file_hash(item['relative_path'])==item['sha256']

def test_production_manifest_hash_unchanged():
    item=next(x for x in BASELINE if x['relative_path'].endswith('/manifest.json'))
    assert file_hash(item['relative_path'])==item['sha256']

def test_phase2b6_outputs_hashes_and_inventory_unchanged():
    expected={x['relative_path'].replace('\\','/') for x in BASELINE if x['scope']=='phase2b6_output'}
    actual={str(p.relative_to(ROOT)).replace('\\','/') for p in (BACKEND/'phase2'/'outputs'/'phase2b6').rglob('*') if p.is_file()}
    assert actual==expected
    for item in BASELINE:
        if item['scope']=='phase2b6_output': assert file_hash(item['relative_path'])==item['sha256']

def test_architecture_decision_and_phase2b6_status_are_locked():
    decision=json.loads((OUT/'architecture_decision.json').read_text(encoding='utf-8'))
    frozen=json.loads((BACKEND/'phase2'/'outputs'/'phase2b6'/'phase2b6_summary.json').read_text(encoding='utf-8'))
    assert decision['status']=='PHASE_2C_REQUIRES_EVIDENCE_EXTENSION'
    assert frozen['status']=='PHASE_2B6_INCONCLUSIVE'
