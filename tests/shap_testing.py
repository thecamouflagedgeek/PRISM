import pandas as pd
import shap
import xgboost as xgb
from sklearn.model_selection import train_test_split

df = pd.read_csv("tests/dataset/credit_dataset_small.csv")
df["target"] = df["loan_status"].apply(lambda x: 1 if x == "Charged Off" else 0)

features = ["loan_amnt", "annual_inc", "dti", "delinq_2yrs"]
X = df[features]
y = df["target"]
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

model = xgb.XGBClassifier()
model.fit(X_train, y_train)

explainer = shap.TreeExplainer(model)
sample = X_test.iloc[[0]]

shap_values = explainer.shap_values(sample)

print("\nbase")
print("Prediction:", model.predict(sample))

print("\nshap values")
for i, col in enumerate(features):
    print(f"{col}: {shap_values[0][i]}")
print("\nconsistency check")

shap_values_1 = explainer.shap_values(sample)
shap_values_2 = explainer.shap_values(sample)

print("Same explanation?",
      (shap_values_1 == shap_values_2).all())

#modify one feature
modified_sample = sample.copy()
modified_sample["annual_inc"] = modified_sample["annual_inc"] * 2

shap_values_modified = explainer.shap_values(modified_sample)

print("\nOriginal annual_inc SHAP:", shap_values[0][1])
print("Modified annual_inc SHAP:", shap_values_modified[0][1])
importance = list(zip(features, shap_values[0]))
importance.sort(key=lambda x: abs(x[1]), reverse=True)

print("Top influencing factors:")
for feat, val in importance:
    print(f"{feat}: {val}")