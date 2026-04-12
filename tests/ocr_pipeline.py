import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
import cv2
import os
import pandas as pd
import re

BASE_DIR = os.path.dirname(__file__)

folders = ["clean", "noisy", "tampered"]
data = []

def extract_pan(text):
    match = re.search(r"[A-Z]{5}[0-9]{4}[A-Z]", text)
    return match.group() if match else "NOT_FOUND"

for folder in folders:
    path = os.path.join(BASE_DIR, "dataset", "images", folder)
    for file in os.listdir(path):
        if file.endswith(".png"):
            img_path = os.path.join(path, file)
            img = cv2.imread(img_path)

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Thresholding (very important)
            _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            thresh = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            text = pytesseract.image_to_string(thresh, config='--psm 6')

            pan = extract_pan(text)

            data.append({
                "image_name": file,
                "folder": folder,
                "predicted_pan": pan
            })

df = pd.DataFrame(data)
df.to_csv(os.path.join(BASE_DIR, "predictions.csv"), index=False)

print("OCR completed. Predictions saved.")