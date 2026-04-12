from PIL import Image, ImageDraw
import csv
import os

os.makedirs("images/clean", exist_ok=True)

data = [
    ("pan_04.png", "Neha Kapoor", "PQRST3456U"),
    ("pan_05.png", "Arjun Singh", "UVWXY7890Z"),
    ("pan_06.png", "Sneha Iyer", "ZXCVB1122Q"),
    ("pan_07.png", "Rohit Das", "ASDFG3344L"),
]

with open("labels/ground_truth.csv", "a", newline="") as f:
    writer = csv.writer(f)

    for filename, name, pan in data:
        img = Image.new('RGB', (600, 300), 'white')
        d = ImageDraw.Draw(img)

        d.text((50, 50), f"Name: {name}", fill=(0, 0, 0))
        d.text((50, 100), f"PAN: {pan}", fill=(0, 0, 0))

        img.save(f"images/clean/{filename}")

        writer.writerow([filename, "pan", name, pan, "", "", "clean"])