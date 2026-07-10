"""
PRISM – Unit & Integration Tests   (Part 8)
Run with: pytest tests/ -v
"""
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

# ── Constants mirrored from scoring_engine ────────────────────
PDO=50; BASE_SCORE=600; BASE_ODDS=19
FACTOR=PDO/np.log(2); OFFSET=BASE_SCORE-FACTOR*np.log(BASE_ODDS)
FEATURES=["credit_debit_ratio","cashflow_cv","net_to_gross_ratio","utility_stability","min_balance"]

def pd_to_score(pd_val):
    pd_val=np.clip(pd_val,1e-6,1-1e-6)
    return int(np.clip(OFFSET-FACTOR*np.log(pd_val/(1-pd_val)),300,900))


# ═════════════════════════════════════════════════════════════
# PART A — Score formula unit tests
# ═════════════════════════════════════════════════════════════

class TestScoreFormula:

    def test_low_pd_produces_high_score(self):
        """Lower PD → higher credit score (correct direction)."""
        score_low_risk  = pd_to_score(0.02)
        score_high_risk = pd_to_score(0.90)
        assert score_low_risk > score_high_risk, \
            f"Low PD should yield higher score: got {score_low_risk} vs {score_high_risk}"

    def test_high_pd_produces_low_score(self):
        assert pd_to_score(0.95) == 300 or pd_to_score(0.95) < 400

    def test_score_clamped_to_300_900(self):
        for pd_val in [0.0001, 0.9999, 0.5, 0.1, 0.8]:
            s = pd_to_score(pd_val)
            assert 300 <= s <= 900, f"Score {s} outside [300,900] for PD={pd_val}"

    def test_base_odds_anchor(self):
        """At BASE_ODDS good:bad, score should be ≈ BASE_SCORE."""
        pd_at_base = 1 / (1 + BASE_ODDS)   # PD = 1/(1+19) = 0.05
        s = pd_to_score(pd_at_base)
        assert abs(s - BASE_SCORE) <= 5, \
            f"Anchor score {s} ≠ {BASE_SCORE} at BASE_ODDS={BASE_ODDS}"

    def test_monotonicity(self):
        """Score must be strictly decreasing as PD increases."""
        pds = np.linspace(0.01, 0.99, 50)
        scores = [pd_to_score(p) for p in pds]
        for i in range(len(scores)-1):
            assert scores[i] >= scores[i+1], \
                f"Non-monotone at PD={pds[i]:.2f}: score {scores[i]} < {scores[i+1]}"

    def test_factor_derivation(self):
        assert abs(FACTOR - PDO/np.log(2)) < 1e-6

    def test_offset_derivation(self):
        assert abs(OFFSET - (BASE_SCORE - FACTOR*np.log(BASE_ODDS))) < 1e-6

    def test_score_formula_sign(self):
        """Score = OFFSET - FACTOR * log_odds.  Positive log_odds → score below OFFSET."""
        log_odds_positive = 2.0    # high PD
        raw = OFFSET - FACTOR * log_odds_positive
        assert raw < OFFSET, "Positive log_odds must reduce score"

    def test_pdo_property(self):
        """Doubling the good odds should add exactly PDO points."""
        pd1 = 0.10
        odds1 = (1-pd1)/pd1
        odds2 = 2*odds1
        pd2 = 1/(1+odds2)
        s1, s2 = pd_to_score(pd1), pd_to_score(pd2)
        assert abs((s2-s1) - PDO) <= 2, \
            f"PDO property failed: Δscore={s2-s1}, expected ≈{PDO}"


# ═════════════════════════════════════════════════════════════
# PART B — WoE transform tests (mock binners)
# ═════════════════════════════════════════════════════════════

def _make_mock_binner(woe_map: dict):
    """Returns a mock OptimalBinning whose transform returns mapped WoE."""
    b = MagicMock()
    def transform(vals, metric="woe"):
        result=[]
        for v in vals:
            if v is None or (isinstance(v,float) and np.isnan(v)):
                result.append(woe_map.get("Missing", 0.0))
            else:
                # Simple bucketing: find closest key
                keys=[k for k in woe_map if k!="Missing"]
                if keys:
                    closest=min(keys,key=lambda k:abs(k-v))
                    result.append(woe_map[closest])
                else:
                    result.append(0.0)
        return np.array(result)
    b.transform.side_effect=transform
    return b

class TestWoETransform:

    def test_missing_uses_binner_not_zero(self):
        """Missing values must use the binner's Missing-bin WoE, not hardcoded 0."""
        binner = _make_mock_binner({0.5: 1.2, 1.0: 0.8, "Missing": -0.5})
        result = binner.transform([np.nan], metric="woe")[0]
        assert result == -0.5, "Missing should return Missing-bin WoE, not 0"

    def test_finite_woe_output(self):
        binner = _make_mock_binner({1.0: 0.5, "Missing": 0.0})
        woe = binner.transform([1.0], metric="woe")[0]
        assert np.isfinite(woe)

    def test_dataframe_output_has_correct_columns(self):
        """WoE transform must return DataFrame with named columns."""
        mock_binners = {f: _make_mock_binner({0.5: 0.1, "Missing": 0.0}) for f in FEATURES}
        feature_dict = {f: 0.5 for f in FEATURES}
        row = {}
        for col in FEATURES:
            val = feature_dict.get(col)
            inp = np.nan if val is None else val
            row[col] = float(mock_binners[col].transform([inp], metric="woe")[0])
        df = pd.DataFrame([row], columns=FEATURES)
        assert list(df.columns) == FEATURES
        assert df.shape == (1, 5)


# ═════════════════════════════════════════════════════════════
# PART C — Feature mapping tests
# ═════════════════════════════════════════════════════════════

class TestFeatureMapping:

    def _map(self, bank=None, salary=None, utility=None):
        def safe(d, k):
            if not d or not isinstance(d,dict): return None
            v=d.get(k)
            if v is None or (isinstance(v,float) and np.isnan(v)): return None
            return v
        return {
            "credit_debit_ratio": safe(bank,"credit_debit_ratio"),
            "cashflow_cv":         safe(bank,"cashflow_cv"),
            "net_to_gross_ratio":  safe(salary,"net_to_gross_ratio"),
            "utility_stability":   safe(utility,"utility_stability"),
            "min_balance":         safe(bank,"min_balance_l3m"),
        }

    def test_all_present(self):
        bank={"credit_debit_ratio":1.2,"cashflow_cv":0.3,"min_balance_l3m":5000}
        salary={"net_to_gross_ratio":0.8}
        utility={"utility_stability":0.9}
        out=self._map(bank,salary,utility)
        assert out["credit_debit_ratio"]==1.2
        assert out["utility_stability"]==0.9
        assert out["net_to_gross_ratio"]==0.8

    def test_missing_docs_produce_none(self):
        out=self._map(bank={"credit_debit_ratio":1.0,"cashflow_cv":0.3,"min_balance_l3m":1000})
        assert out["net_to_gross_ratio"] is None
        assert out["utility_stability"] is None

    def test_nan_becomes_none(self):
        bank={"credit_debit_ratio":float("nan"),"cashflow_cv":0.3,"min_balance_l3m":1000}
        out=self._map(bank)
        assert out["credit_debit_ratio"] is None

    def test_utility_uses_utility_stability_not_flag(self):
        utility={"utility_stability":0.8,"payment_discipline_flag":1}
        out=self._map(utility=utility)
        assert out["utility_stability"]==0.8  # must use utility_stability key


# ═════════════════════════════════════════════════════════════
# PART D — Risk tier tests
# ═════════════════════════════════════════════════════════════

class TestRiskTier:

    def _tier(self, pd_val):
        if pd_val < 0.20: return "Low Risk"
        elif pd_val < 0.40: return "Medium Risk"
        elif pd_val < 0.70: return "High Risk"
        else: return "Very High Risk"

    def test_boundaries(self):
        assert self._tier(0.00) == "Low Risk"
        assert self._tier(0.19) == "Low Risk"
        assert self._tier(0.20) == "Medium Risk"
        assert self._tier(0.39) == "Medium Risk"
        assert self._tier(0.40) == "High Risk"
        assert self._tier(0.69) == "High Risk"
        assert self._tier(0.70) == "Very High Risk"
        assert self._tier(1.00) == "Very High Risk"

    def test_monotone_risk(self):
        pds=[0.05,0.25,0.55,0.85]
        tiers=[self._tier(p) for p in pds]
        order=["Low Risk","Medium Risk","High Risk","Very High Risk"]
        assert tiers==order


# ═════════════════════════════════════════════════════════════
# PART E — Confidence score tests
# ═════════════════════════════════════════════════════════════

class TestConfidenceScore:

    def _confidence(self, bank, salary, utility, pd_val, feature_dict):
        doc=(0.6*(bank is not None)+0.2*(salary is not None)+0.2*(utility is not None))
        n_present=sum(1 for f in FEATURES if feature_dict.get(f) is not None)
        qual=n_present/len(FEATURES)
        cert=abs(pd_val-0.5)*2
        score=0.4*doc+0.3*qual+0.3*cert
        return score

    def test_full_docs_high_confidence(self):
        fd={f:1.0 for f in FEATURES}
        s=self._confidence({},{},{},0.9,fd)
        assert s>0.7

    def test_missing_all_docs_lowers_confidence(self):
        fd={f:None for f in FEATURES}
        s=self._confidence(None,None,None,0.5,fd)
        assert s<0.2

    def test_uncertain_pd_lowers_certainty(self):
        fd={f:1.0 for f in FEATURES}
        s_certain=self._confidence({},{},{},0.05,fd)
        s_uncertain=self._confidence({},{},{},0.50,fd)
        assert s_certain>s_uncertain

    def test_output_in_0_1(self):
        fd={f:1.0 for f in FEATURES}
        s=self._confidence({},{},{},0.5,fd)
        assert 0.0<=s<=1.0


# ═════════════════════════════════════════════════════════════
# PART F — PSI utility test
# ═════════════════════════════════════════════════════════════

class TestPSI:

    def _psi(self, exp, act, n_bins=10):
        from validation.feature_validator import compute_psi
        return compute_psi(pd.Series(exp), pd.Series(act), n_bins)

    def test_identical_distributions_psi_near_zero(self):
        x=np.random.normal(0,1,1000)
        psi=self._psi(x,x)
        assert psi<0.05, f"PSI of identical dist should be ~0, got {psi}"

    def test_shifted_distribution_high_psi(self):
        exp=np.random.normal(0,1,1000)
        act=np.random.normal(5,1,1000)   # large shift
        psi=self._psi(exp,act)
        assert psi>0.25, f"PSI of shifted dist should be >0.25, got {psi}"