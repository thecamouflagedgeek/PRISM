"""
Credit Scorecard Logistic Regression Module
Siddiqi (2006), Thomas (2002), Hosmer-Lemeshow (2000), Basel II IRB aligned

Core Features:
- WoE-based Logistic Regression
- L2 regularization (stability)
- Class imbalance handling
- Wald significance test
- VIF multicollinearity check
- KS / AUC / Gini / HL calibration
- Scorecard-ready additive structure
"""

import numpy as np
import pandas as pd
import warnings
from scipy import stats

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────
# 1. MODEL FITTING
# ─────────────────────────────────────────────

def fit_logistic_regression(X_train_woe: pd.DataFrame,
                            y_train: pd.Series) -> LogisticRegression:
    """
    Fit Logistic Regression on WoE features.
    """

    model = LogisticRegression(
        solver="lbfgs",
        C=1.0,
        max_iter=1000,
        class_weight="balanced",
        random_state=42
    )

    model.fit(X_train_woe, y_train)

    print("\n[LOG REG] Model trained successfully")
    print(f"Intercept (β0): {model.intercept_[0]:.6f}")

    return model


# ─────────────────────────────────────────────
# 2. PREDICTION UTILITIES
# ─────────────────────────────────────────────

def predict_proba(model, X: pd.DataFrame):
    return np.clip(model.predict_proba(X)[:, 1], 1e-6, 1 - 1e-6)


def log_odds(model, X: pd.DataFrame):
    p = predict_proba(model, X)
    return np.log(p / (1 - p))


# ─────────────────────────────────────────────
# 3. COEFFICIENT TABLE (WALD TEST)
# ─────────────────────────────────────────────

def coefficient_table(model, X_train, y_train):
    """
    Wald test significance table
    """

    X = X_train.values
    y = y_train.values

    p_hat = model.predict_proba(X)[:, 1]
    p_hat = np.clip(p_hat, 1e-6, 1 - 1e-6)

    W = np.diag(p_hat * (1 - p_hat))

    XtWX = X.T @ W @ X
    XtWX += np.eye(XtWX.shape[0]) * 1e-8  # stability

    cov_matrix = np.linalg.pinv(XtWX)
    std_err = np.sqrt(np.diag(cov_matrix))

    coef = model.coef_[0]

    wald_stat = (coef / (std_err + 1e-8)) ** 2
    p_values = 1 - stats.chi2.cdf(wald_stat, df=1)

    return pd.DataFrame({
        "feature": X_train.columns,
        "coefficient": coef,
        "std_error": std_err,
        "wald_stat": wald_stat,
        "p_value": p_values,
        "significant": np.where(p_values < 0.05, "✓", "✗")
    }).sort_values("p_value")


# ─────────────────────────────────────────────
# 4. VIF CHECK
# ─────────────────────────────────────────────

def compute_vif(X: pd.DataFrame):
    from sklearn.linear_model import LinearRegression

    results = []

    for col in X.columns:
        X_other = X.drop(columns=[col]).values
        y_col = X[col].values

        model = LinearRegression().fit(X_other, y_col)
        r2 = model.score(X_other, y_col)

        vif = 1 / (1 - r2 + 1e-10)

        results.append({
            "feature": col,
            "VIF": vif,
            "status": "OK" if vif < 10 else "HIGH"
        })

    return pd.DataFrame(results)


# ─────────────────────────────────────────────
# 5. KS STATISTIC (FIXED)
# ─────────────────────────────────────────────

def ks_statistic(y_true, y_prob):
    df = pd.DataFrame({"y": y_true, "p": y_prob})
    df = df.sort_values("p", ascending=False)

    bad = (df["y"] == 1).sum()
    good = (df["y"] == 0).sum()

    df["cum_bad"] = (df["y"] == 1).cumsum() / (bad + 1e-8)
    df["cum_good"] = (df["y"] == 0).cumsum() / (good + 1e-8)

    ks = (df["cum_bad"] - df["cum_good"]).abs().max()

    return round(ks * 100, 2)


# ─────────────────────────────────────────────
# 6. GINI / AUC
# ─────────────────────────────────────────────

def gini_score(y_true, y_prob):
    auc = roc_auc_score(y_true, y_prob)
    return round(2 * auc - 1, 4), round(auc, 4)


# ─────────────────────────────────────────────
# 7. HOSMER-LEMESHOW (FIXED)
# ─────────────────────────────────────────────

def hosmer_lemeshow(y_true, y_prob, bins=10):
    df = pd.DataFrame({"y": y_true, "p": y_prob})
    df["bin"] = pd.qcut(df["p"], bins, duplicates="drop")

    grouped = df.groupby("bin").agg(
        obs=("y", "sum"),
        exp=("p", "sum"),
        n=("y", "count")
    )

    eps = 1e-8
    hl = (((grouped["obs"] - grouped["exp"]) ** 2) /
          (grouped["exp"] + eps)).sum()

    df_stat = len(grouped) - 2
    p = 1 - stats.chi2.cdf(hl, df=df_stat)

    return {
        "hl_stat": round(hl, 4),
        "p_value": round(p, 4),
        "calibration": "GOOD" if p > 0.05 else "BAD"
    }


# ─────────────────────────────────────────────
# 8. FULL EVALUATION PIPELINE
# ─────────────────────────────────────────────

def evaluate_model(model, X_train, y_train, X_test, y_test):

    results = {}

    for name, X, y in [
        ("train", X_train, y_train),
        ("test", X_test, y_test)
    ]:

        prob = predict_proba(model, X)

        auc = roc_auc_score(y, prob)
        gini, _auc = gini_score(y, prob)
        ks = ks_statistic(y, prob)
        hl = hosmer_lemeshow(y, prob)

        results[name] = {
            "AUC": round(auc, 4),
            "Gini": gini,
            "KS": ks,
            "HL": hl
        }

    return results


# ─────────────────────────────────────────────
# 9. PRINT REPORT
# ─────────────────────────────────────────────

def print_report(results):

    print("\n================ MODEL REPORT ================\n")

    for k, v in results.items():
        print(f"[{k.upper()}]")
        print(f"AUC  : {v['AUC']}")
        print(f"GINI : {v['Gini']}")
        print(f"KS   : {v['KS']}")
        print(f"HL   : {v['HL']}")
        print("------------------------------------")

    gap = results["train"]["AUC"] - results["test"]["AUC"]
    print(f"\nAUC DROP: {round(gap, 4)}")

    if gap > 0.03:
        print("⚠ Overfitting risk detected")
    else:
        print("✓ Model stable")

def print_evaluation(results):
    print_report(results)