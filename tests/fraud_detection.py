import pandas as pd
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score, accuracy_score

df = pd.read_csv("dataset/fraud_detection.csv")

def fraud_logic(row):
    score = 0

    if row["loan_count_30d"] > 3:
        score += 1
    if row["location_match"] == 0:
        score += 1
    if row["avg_loan_amount"] > row["income"] * 0.5:
        score += 1
    if row["employment_stability"] == 0:
        score += 1
    return 1 if score >= 2 else 0

df["predicted_label"] = df.apply(fraud_logic, axis=1)

y_true = df["label"]
y_pred = df["predicted_label"]

tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

print("\nCONFUSION MATRIX")
print(f"TP: {tp}, TN: {tn}, FP: {fp}, FN: {fn}")

precision = precision_score(y_true, y_pred)
recall = recall_score(y_true, y_pred)
f1 = f1_score(y_true, y_pred)
accuracy = accuracy_score(y_true, y_pred)

print("\nMETRICS")
print("Accuracy:", round(accuracy, 2))
print("Precision:", round(precision, 2))
print("Recall:", round(recall, 2))
print("F1 Score:", round(f1, 2))

print("\nERROR ANALYSIS")

fp_cases = df[(y_true == 0) & (y_pred == 1)]
fn_cases = df[(y_true == 1) & (y_pred == 0)]

print("\nFalse Positives (Genuine flagged as Fraud):")
print(fp_cases[["pan", "loan_count_30d", "income"]])

print("\nFalse Negatives (Fraud missed by model):")
print(fn_cases[["pan", "loan_count_30d", "income"]])