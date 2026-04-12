import cv2
import os
import random
import string
BASE_DIR = os.path.dirname(__file__)
clean_path = os.path.join(BASE_DIR, "images", "clean")
tampered_path = os.path.join(BASE_DIR, "images", "tampered")

os.makedirs(tampered_path, exist_ok=True)

def generate_fake_pan():
    letters = ''.join(random.choices(string.ascii_uppercase, k=5))
    digits = ''.join(random.choices(string.digits, k=4))
    last = random.choice(string.ascii_uppercase)
    return letters + digits + last

for file in os.listdir(clean_path):
    if file.endswith(".png"):
        img_path = os.path.join(clean_path, file)
        img = cv2.imread(img_path)
        tampered = img.copy()

        #location of the pan number
        x, y = 50, 100  
        cv2.rectangle(tampered, (x, y), (x + 300, y + 40), (255, 255, 255), -1)
        fake_pan = generate_fake_pan()
        cv2.putText(
            tampered,
            f"PAN: {fake_pan}",
            (x, y + 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 0),
            2,
            cv2.LINE_AA
        )
        new_name = f"tampered_{file}"
        cv2.imwrite(os.path.join(tampered_path, new_name), tampered)

        print(f"Tampered created: {new_name} | Fake PAN: {fake_pan}")