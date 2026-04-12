import pandas as pd
import os

BASE_DIR = os.path.dirname(__file__)
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
gt = pd.read_csv(os.path.join(DATASET_DIR, "labels", "ground_truth.csv"))
pred = pd.read_csv(os.path.join(DATASET_DIR, "predictions.csv"))
merged = pd.merge(gt, pred, on="image_name")

#field accuracy
correct_fields = (merged["pan"] == merged["predicted_pan"]).sum()
total_fields = len(merged)

field_accuracy = correct_fields / total_fields

#character accuracy
def char_acc(a, b):
    a, b = str(a), str(b)
    matches = sum(1 for x, y in zip(a, b) if x == y)
    return matches / max(len(a), len(b))

merged["char_acc"] = merged.apply(
    lambda row: char_acc(row["pan"], row["predicted_pan"]),
    axis=1
)

char_accuracy = merged["char_acc"].mean()

def predict_label(row):
    return "tampered" if row["pan"] != row["predicted_pan"] else "clean"

merged["predicted_label"] = merged.apply(predict_label, axis=1)
if "label" not in merged.columns:
    merged["label"] = merged["folder"].apply(
        lambda x: "tampered" if x == "tampered" else "clean"
    )

tamper_accuracy = (merged["label"] == merged["predicted_label"]).mean()
tp = len(merged[(merged["label"] == "tampered") &
                (merged["predicted_label"] == "tampered")])

fp = len(merged[(merged["label"] == "clean") &
                (merged["predicted_label"] == "tampered")])

precision = tp / (tp + fp) if (tp + fp) != 0 else 0

print("\nOCR EVALUATION")
print(f"Field Accuracy: {field_accuracy:.2f}")
print(f"Character Accuracy: {char_accuracy:.2f}")

print("\nTAMPER DETECTION")
print(f"Accuracy: {tamper_accuracy:.2f}")
print(f"Precision: {precision:.2f}")