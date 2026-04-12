
import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, roc_auc_score, confusion_matrix
)

from xgboost import XGBClassifier

df = pd.read_csv("dataset/credit_data.csv")  

df = df[df["loan_status"].isin(["Fully Paid", "Charged Off"])]

df["target"] = df["loan_status"].apply(
    lambda x: 0 if x == "Fully Paid" else 1
)
features = [
    "loan_amnt", "int_rate", "annual_inc",
    "dti", "fico_range_low", "fico_range_high",
    "emp_length", "purpose"
]

df = df[features + ["target"]].dropna()
le = LabelEncoder()
df["emp_length"] = le.fit_transform(df["emp_length"])
df["purpose"] = le.fit_transform(df["purpose"])
X = df.drop("target", axis=1)
y = df["target"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)
model = XGBClassifier(
    max_depth=4,
    learning_rate=0.1,
    n_estimators=100,
    eval_metric="logloss"
)

model.fit(X_train, y_train)
y_pred = model.predict(X_test)
y_prob = model.predict_proba(X_test)[:, 1]

print("\nModel metrics")

accuracy = accuracy_score(y_test, y_pred)
precision = precision_score(y_test, y_pred)
recall = recall_score(y_test, y_pred)
f1 = f1_score(y_test, y_pred)
roc_auc = roc_auc_score(y_test, y_prob)

print("Accuracy:", round(accuracy, 3))
print("Precision:", round(precision, 3))
print("Recall:", round(recall, 3))
print("F1 Score:", round(f1, 3))
print("ROC-AUC:", round(roc_auc, 3))

tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()

print("\nConfusion Matrix")
print(f"TP (Correct Defaults): {tp}")
print(f"TN (Correct Non-Defaults): {tn}")
print(f"FP (False Approval - BAD UX): {fp}")
print(f"FN (Missed Default - RISK): {fn}")
cv_scores = cross_val_score(model, X, y, cv=5, scoring="roc_auc")

print("ROC-AUC Scores:", cv_scores)
print("Mean ROC-AUC:", round(cv_scores.mean(), 3))

print("\n Threshold Analysis")

for threshold in [0.5, 0.6, 0.7]:
    y_pred_thresh = (y_prob > threshold).astype(int)

    precision_t = precision_score(y_test, y_pred_thresh)
    recall_t = recall_score(y_test, y_pred_thresh)

    print(f"\nThreshold: {threshold}")
    print("Precision:", round(precision_t, 3))
    print("Recall:", round(recall_t, 3))