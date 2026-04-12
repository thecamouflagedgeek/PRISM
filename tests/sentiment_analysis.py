import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
)

df = pd.read_csv("tests/dataset/sentiment.csv")
X_text = df["loan_description"]
y = df["label"]

vectorizer = TfidfVectorizer(stop_words="english")
X_text_vec = vectorizer.fit_transform(X_text)

# Train-test split
X_train_text, X_test_text, y_train, y_test, idx_train, idx_test = train_test_split(
    X_text_vec, y, df.index, test_size=0.2, random_state=42
)

text_model = LogisticRegression()
text_model.fit(X_train_text, y_train)
text_pred = text_model.predict(X_test_text)

def behaviour_model(row):
    risk = 0
    
    if row["variance_income"] > 15000:
        risk += 1
    if row["bill_delay_days"] > 10:
        risk += 1
    if row["job_changes"] > 2:
        risk += 1
        
    return 1 if risk >= 2 else 0

df_test = df.loc[idx_test].copy()
df_test["behaviour_pred"] = df_test.apply(behaviour_model, axis=1)
#model 
df_test["text_pred"] = text_pred

def final_model(row):
    # If either says risky → risky
    if row["text_pred"] == 1 or row["behaviour_pred"] == 1:
        return 1
    return 0

df_test["final_pred"] = df_test.apply(final_model, axis=1)

y_true = df_test["label"]
y_pred = df_test["final_pred"]

print("Accuracy:", round(accuracy_score(y_true, y_pred), 3))
print("Precision:", round(precision_score(y_true, y_pred), 3))
print("Recall:", round(recall_score(y_true, y_pred), 3))
print("F1 Score:", round(f1_score(y_true, y_pred), 3))


tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

print("\nMatrix")
print("TP (Correct Risk Detected):", tp)
print("TN (Correct Safe Detected):", tn)
print("FP (False Alarm - BAD UX):", fp)
print("FN (Missed Risk - DANGEROUS):", fn)
print("\nFalse Positives (Safe but flagged risky):")
print(df_test[(df_test["label"] == 0) & (df_test["final_pred"] == 1)][
    ["loan_description", "monthly_income"]
])
print("\nFalse Negatives (Risk but missed):")
print(df_test[(df_test["label"] == 1) & (df_test["final_pred"] == 0)][
    ["loan_description", "monthly_income"]
])
portfolio_risk = df_test["final_pred"].mean()
print("\nPortfolio Risk Score:", round(portfolio_risk, 3))