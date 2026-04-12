import cv2
import numpy as np
import os
import random
BASE_DIR = os.path.dirname(__file__)
clean_path = os.path.join(BASE_DIR, "images", "clean")
noisy_path = os.path.join(BASE_DIR, "images", "noisy")

os.makedirs(noisy_path, exist_ok=True)
def add_gaussian_noise(image):
    noise = np.random.normal(0, 25, image.shape).astype(np.uint8)
    return cv2.add(image, noise)

def add_blur(image):
    return cv2.GaussianBlur(image, (5, 5), 0)

def adjust_brightness(image):
    value = random.randint(-50, 50)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    v = np.clip(v + value, 0, 255).astype(np.uint8)
    final_hsv = cv2.merge((h, s, v))
    return cv2.cvtColor(final_hsv, cv2.COLOR_HSV2BGR)

def rotate_image(image):
    angle = random.randint(-10, 10)
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w//2, h//2), angle, 1)
    return cv2.warpAffine(image, matrix, (w, h))
for file in os.listdir(clean_path):
    if file.endswith(".png"):
        img_path = os.path.join(clean_path, file)
        img = cv2.imread(img_path)

        noisy = img.copy()

        if random.choice([True, False]):
            noisy = add_gaussian_noise(noisy)

        if random.choice([True, False]):
            noisy = add_blur(noisy)

        if random.choice([True, False]):
            noisy = adjust_brightness(noisy)

        if random.choice([True, False]):
            noisy = rotate_image(noisy)

        new_name = f"noisy_{file}"
        cv2.imwrite(os.path.join(noisy_path, new_name), noisy)

        print(f"Noisy image created: {new_name}")