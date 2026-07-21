"""
PRISM – Automated Evaluation Report Generator   (Part 11)
Generates a self-contained HTML validation report.
Run: python -m validation.report_generator --model artifacts/lr_model.pkl
                                           --binning artifacts/binning.pkl
                                           --data data/validation.csv
                                           --output reports/validation_report.html
"""
from __future__ import annotations
import argparse, json, sys, os
from datetime import datetime
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

_CSS = """
<style>
  body{font-family:'Segoe UI',sans-serif;background:#f5f7fa;color:#222;margin:0;padding:0}
  .header{background:#1a2340;color:#fff;padding:32px 48px}
  .header h1{margin:0;font-size:2rem;letter-spacing:1px}
  .header p{margin:6px 0 0;opacity:.7;font-size:.95rem}
  .container{max-width:1100px;margin:0 auto;padding:32px 24px}
  .section{background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.07);
            margin-bottom:28px;padding:28px 32px}
  .section h2{color:#1a2340;border-bottom:2px solid #e5e9f0;padding-bottom:8px;margin-top:0}
  table{border-collapse:collapse;width:100%;font-size:.88rem}
  th{background:#f0f3f8;color:#1a2340;text-align:left;padding:8px 12px}
  td{padding:7px 12px;border-bottom:1px solid #eef0f4}
  tr:hover td{background:#fafbfd}
  .badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:.78rem;font-weight:600}
  .pass{background:#d4edda;color:#155724}
  .fail{background:#f8d7da;color:#721c24}
  .warn{background:#fff3cd;color:#856404}
  .metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-top:16px}
  .metric-card{background:#f8f9fc;border-radius:8px;padding:16px;text-align:center}
  .metric-card .val{font-size:1.6rem;font-weight:700;color:#1a2340}
  .metric-card .lbl{font-size:.78rem;color:#666;margin-top:4px}
  .warn-list{margin:0;padding-left:20px}
  .warn-list li{color:#856404;background:#fffbf0;margin:3px 0;padding:4px 8px;border-radius:4px;font-size:.85rem}
  .err-list li{color:#721c24;background:#fff5f5;margin:3px 0;padding:4px 8px;border-radius:4px;font-size:.85rem}
  .summary-bar{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px}
  .summary-pill{padding:8px 20px;border-radius:20px;font-weight:600;font-size:.92rem}
</style>
"""

def _badge(passed: bool) -> str:
    cls = "pass" if passed else "fail"
    txt = "PASS" if passed else "FAIL"
    return f'<span class="badge {cls}">{txt}</span>'

def _fmt(v, decimals=4):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.{decimals}f}"
    return str(v)

def _warn_html(warnings):
    if not warnings: return "<em style='color:#888'>None</em>"
    items = "".join(f"<li>{w}</li>" for w in warnings)
    return f'<ul class="warn-list">{items}</ul>'


def generate_report(
    feature_reports,
    bin_reports,
    woe_tests,
    model_report,
    calibration_report,
    score_report,
    output_path: str = "reports/prism_validation_report.html",
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Summary counts ────────────────────────────────────────
    all_checks = [
        *(r.passed for r in feature_reports.values()),
        *(r.passed for r in bin_reports.values()),
        *(t.passed for t in woe_tests),
        model_report.passed,
        score_report.passed,
    ]
    n_pass = sum(all_checks); n_fail = len(all_checks) - n_pass
    overall = "PASS" if n_fail == 0 else "FAIL"
    overall_cls = "pass" if n_fail == 0 else "fail"

    # ── Feature table ─────────────────────────────────────────
    feat_rows = ""
    for feat, r in feature_reports.items():
        feat_rows += f"""
        <tr>
          <td><strong>{feat}</strong></td>
          <td>{r.n}</td>
          <td>{r.missing_rate:.1%}</td>
          <td>{_fmt(r.mean,2)}</td>
          <td>{_fmt(r.std,2)}</td>
          <td>{_fmt(r.p50,2)}</td>
          <td>{_fmt(r.outlier_rate,3)}</td>
          <td>{_fmt(r.psi,3) if r.psi is not None else '—'}</td>
          <td>{_badge(r.passed)}</td>
        </tr>
        <tr><td colspan="9" style="padding:0 12px 8px;">{_warn_html(r.warnings)}</td></tr>"""

    # ── Binning table ─────────────────────────────────────────
    bin_rows = ""
    for feat, r in bin_reports.items():
        bin_rows += f"""
        <tr>
          <td><strong>{feat}</strong></td>
          <td>{r.n_bins}</td>
          <td>{_fmt(r.iv,4)}</td>
          <td>{"✓" if r.monotonic else "✗"}</td>
          <td>{r.min_bin_count}</td>
          <td>{r.empty_bins}</td>
          <td>{r.woe_values}</td>
          <td>{_badge(r.passed)}</td>
        </tr>
        <tr><td colspan="8" style="padding:0 12px 8px;">{_warn_html(r.warnings)}</td></tr>"""

    # ── WoE test table ────────────────────────────────────────
    woe_rows = ""
    for t in woe_tests:
        woe_rows += f"""
        <tr>
          <td>{t.feature}</td>
          <td>{_fmt(t.input_value,4)}</td>
          <td>{_fmt(t.woe_output,4)}</td>
          <td>{_badge(t.passed)}</td>
          <td>{t.note}</td>
        </tr>"""

    # ── Coefficient table ─────────────────────────────────────
    coef_table = model_report.coefficient_table
    coef_rows = ""
    for _, row in coef_table.iterrows():
        sig = "✓" if row.get("significant", False) else "✗"
        coef_rows += f"""
        <tr>
          <td>{row['feature']}</td>
          <td>{_fmt(row['coefficient'],4)}</td>
          <td>{_fmt(row.get('std_error',np.nan),4)}</td>
          <td>{_fmt(row.get('wald_z',np.nan),4)}</td>
          <td>{_fmt(row.get('p_value',np.nan),4)}</td>
          <td>{_fmt(row.get('odds_ratio',np.nan),4)}</td>
          <td>[{_fmt(row.get('ci_lower',np.nan),3)}, {_fmt(row.get('ci_upper',np.nan),3)}]</td>
          <td>{sig}</td>
        </tr>"""

    # ── VIF table ─────────────────────────────────────────────
    vif_rows = ""
    for _, row in model_report.vif_table.iterrows():
        flag = "⚠️" if row["VIF"] > 5 else "✓"
        vif_rows += f"<tr><td>{row['feature']}</td><td>{_fmt(row['VIF'],3)} {flag}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>PRISM Validation Report</title>{_CSS}</head>
<body>
<div class="header">
  <h1>🔷 PRISM Credit Scoring — Validation Report</h1>
  <p>Generated: {now} &nbsp;|&nbsp; Overall: <span class="badge {overall_cls}">{overall}</span>
  &nbsp;|&nbsp; {n_pass} checks passed, {n_fail} failed</p>
</div>
<div class="container">

<!-- SUMMARY -->
<div class="section">
  <h2>Executive Summary</h2>
  <div class="metric-grid">
    <div class="metric-card"><div class="val">{model_report.auc:.3f}</div><div class="lbl">AUC-ROC</div></div>
    <div class="metric-card"><div class="val">{model_report.gini:.3f}</div><div class="lbl">Gini</div></div>
    <div class="metric-card"><div class="val">{model_report.ks_statistic:.3f}</div><div class="lbl">KS Statistic</div></div>
    <div class="metric-card"><div class="val">{calibration_report.brier_score:.3f}</div><div class="lbl">Brier Score</div></div>
    <div class="metric-card"><div class="val">{calibration_report.ece:.3f}</div><div class="lbl">ECE</div></div>
    <div class="metric-card"><div class="val">{calibration_report.hl_p_value:.3f}</div><div class="lbl">HL p-value</div></div>
    <div class="metric-card"><div class="val">{score_report.mean_score:.0f}</div><div class="lbl">Mean Score</div></div>
    <div class="metric-card"><div class="val">{score_report.min_score:.0f}–{score_report.max_score:.0f}</div><div class="lbl">Score Range</div></div>
  </div>
</div>

<!-- PART 1: FEATURES -->
<div class="section">
  <h2>Part 1 — Feature Engineering Validation</h2>
  <table>
    <tr><th>Feature</th><th>N</th><th>Missing</th><th>Mean</th><th>Std</th><th>Median</th><th>Outlier%</th><th>PSI</th><th>Status</th></tr>
    {feat_rows}
  </table>
</div>

<!-- PART 2: BINNING -->
<div class="section">
  <h2>Part 2 — Optimal Binning Validation</h2>
  <table>
    <tr><th>Feature</th><th>Bins</th><th>IV</th><th>Monotonic</th><th>Min Count</th><th>Empty</th><th>WoE Values</th><th>Status</th></tr>
    {bin_rows}
  </table>
</div>

<!-- PART 3: WOE -->
<div class="section">
  <h2>Part 3 — WoE Transform Unit Tests</h2>
  <table>
    <tr><th>Feature</th><th>Input</th><th>WoE Output</th><th>Status</th><th>Note</th></tr>
    {woe_rows}
  </table>
</div>

<!-- PART 4: MODEL -->
<div class="section">
  <h2>Part 4 — Logistic Regression Audit</h2>
  {_warn_html(model_report.warnings)}
  <h3>Coefficient Table (with Wald Statistics)</h3>
  <table>
    <tr><th>Feature</th><th>Coefficient</th><th>Std Error</th><th>Wald Z</th><th>p-value</th><th>Odds Ratio</th><th>95% CI</th><th>Significant</th></tr>
    {coef_rows}
  </table>
  <h3>Variance Inflation Factors</h3>
  <table><tr><th>Feature</th><th>VIF</th></tr>{vif_rows}</table>
</div>

<!-- PART 5: CALIBRATION -->
<div class="section">
  <h2>Part 5 — Probability of Default Calibration</h2>
  <div class="metric-grid">
    <div class="metric-card"><div class="val">{calibration_report.brier_score}</div><div class="lbl">Brier Score (↓ better)</div></div>
    <div class="metric-card"><div class="val">{calibration_report.ece}</div><div class="lbl">ECE (↓ better, threshold 0.10)</div></div>
    <div class="metric-card"><div class="val">{calibration_report.hl_statistic:.2f}</div><div class="lbl">HL Statistic</div></div>
    <div class="metric-card"><div class="val">{calibration_report.hl_p_value:.4f}</div><div class="lbl">HL p-value (↑ better, need >0.05)</div></div>
    <div class="metric-card"><div class="val">{"✓ OK" if calibration_report.hl_passed else "✗ Poor"}</div><div class="lbl">HL Test</div></div>
    <div class="metric-card"><div class="val">{"Yes" if calibration_report.calibration_needed else "No"}</div><div class="lbl">Platt Scaling Needed</div></div>
  </div>
  {_warn_html(calibration_report.warnings)}
</div>

<!-- PART 6: SCORES -->
<div class="section">
  <h2>Part 6 — Credit Score Scaling Validation</h2>
  <div class="metric-grid">
    <div class="metric-card"><div class="val">{score_report.min_score:.0f}</div><div class="lbl">Min Score</div></div>
    <div class="metric-card"><div class="val">{score_report.max_score:.0f}</div><div class="lbl">Max Score</div></div>
    <div class="metric-card"><div class="val">{score_report.mean_score:.1f}</div><div class="lbl">Mean Score</div></div>
    <div class="metric-card"><div class="val">{score_report.std_score:.1f}</div><div class="lbl">Std Dev</div></div>
    <div class="metric-card"><div class="val">{score_report.at_floor_pct:.1%}</div><div class="lbl">At Floor (300)</div></div>
    <div class="metric-card"><div class="val">{score_report.at_ceiling_pct:.1%}</div><div class="lbl">At Ceiling (900)</div></div>
    <div class="metric-card"><div class="val">{"✓" if score_report.direction_correct else "✗"}</div><div class="lbl">Direction Correct</div></div>
    <div class="metric-card"><div class="val">{"⚠️ Yes" if score_report.saturation_warning else "✓ No"}</div><div class="lbl">Saturation</div></div>
  </div>
  {_warn_html(score_report.warnings)}
</div>

<!-- READINESS -->
<div class="section">
  <h2>Deployment Readiness Assessment</h2>
  <table>
    <tr><th>Criterion</th><th>Status</th><th>Note</th></tr>
    <tr><td>Score direction (high PD → low score)</td><td>{_badge(score_report.direction_correct)}</td><td>Critical — must pass</td></tr>
    <tr><td>Score range utilisation (not saturated)</td><td>{_badge(not score_report.saturation_warning)}</td><td>Critical — fix class imbalance if failing</td></tr>
    <tr><td>AUC ≥ 0.65</td><td>{_badge(model_report.auc>=0.65)}</td><td>Minimum discriminatory power</td></tr>
    <tr><td>KS ≥ 0.20</td><td>{_badge(model_report.ks_statistic>=0.20)}</td><td>Separation quality</td></tr>
    <tr><td>Hosmer-Lemeshow p > 0.05</td><td>{_badge(calibration_report.hl_passed)}</td><td>Calibration — apply Platt if failing</td></tr>
    <tr><td>ECE ≤ 0.10</td><td>{_badge(calibration_report.ece<=0.10)}</td><td>Expected calibration error</td></tr>
    <tr><td>No empty bins</td><td>{_badge(all(r.empty_bins==0 for r in bin_reports.values()))}</td><td>Binning stability</td></tr>
    <tr><td>All features significant (p&lt;0.05)</td><td>{_badge(model_report.coefficient_table[model_report.coefficient_table['feature']!='intercept']['significant'].all())}</td><td>Consider removing insignificant features</td></tr>
  </table>
</div>

</div><!-- /container -->
</body></html>"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report written → {output_path}")
    return output_path


def run_full_validation(
    model_path: str,
    binning_path: str,
    data_path: str,
    target_col: str = "default",
    output_path: str = "reports/prism_validation_report.html",
    reference_data_path: Optional[str] = None,
):
    """
    Entry point: load artifacts + data, run all validations, generate HTML report.
    """
    import joblib
    from validation.feature_validator import validate_features, validate_binning, validate_woe_transform
    from validation.model_validator import validate_model, validate_calibration, validate_score_scaling

    print("Loading artifacts...")
    model    = joblib.load(model_path)
    binners  = joblib.load(binning_path)
    df       = pd.read_csv(data_path)
    ref_df   = pd.read_csv(reference_data_path) if reference_data_path else None

    FEATURES = ["credit_debit_ratio","cashflow_cv","net_to_gross_ratio","utility_stability","min_balance"]
    y_true   = df[target_col].values if target_col in df.columns else np.zeros(len(df))

    # WoE transform
    print("Transforming features...")
    woe_rows = []
    for _, row_data in df[FEATURES].iterrows():
        r = {}
        for feat in FEATURES:
            v = row_data[feat]
            inp = np.nan if pd.isna(v) else v
            r[feat] = float(binners[feat].transform([inp], metric="woe")[0])
        woe_rows.append(r)
    X_woe = pd.DataFrame(woe_rows, columns=FEATURES)

    print("Running validations...")
    feat_reports = validate_features(df[FEATURES], ref_df[FEATURES] if ref_df is not None else None)
    bin_reports  = validate_binning(binners)
    woe_tests    = validate_woe_transform(binners)
    model_report = validate_model(model, X_woe, y_true)
    cal_report, _= validate_calibration(model, X_woe, y_true)
    score_report = validate_score_scaling(model, X_woe, y_true)

    return generate_report(feat_reports, bin_reports, woe_tests,
                           model_report, cal_report, score_report, output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model",    required=True)
    parser.add_argument("--binning",  required=True)
    parser.add_argument("--data",     required=True)
    parser.add_argument("--target",   default="default")
    parser.add_argument("--output",   default="reports/prism_validation_report.html")
    parser.add_argument("--reference",default=None)
    args = parser.parse_args()
    run_full_validation(args.model, args.binning, args.data, args.target, args.output, args.reference)