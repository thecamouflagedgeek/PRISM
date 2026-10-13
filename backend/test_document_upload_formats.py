import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
import pytesseract

from route.assessment_routes import save_temp
from ingestion.universal_pipeline import TextExtractor


@pytest.mark.parametrize("filename", ["statement.pdf", "statement.jpg", "statement.jpeg", "statement.png"])
def test_supported_upload_suffix_is_preserved(filename):
    path = asyncio.run(save_temp(UploadFile(filename=filename, file=BytesIO(b"synthetic file bytes"))))
    try:
        assert Path(path).suffix == Path(filename).suffix
    finally:
        Path(path).unlink(missing_ok=True)


def test_unsupported_upload_suffix_is_rejected():
    with pytest.raises(HTTPException) as error:
        asyncio.run(save_temp(UploadFile(filename="statement.csv", file=BytesIO(b"data"))))
    assert error.value.status_code == 415


@pytest.mark.parametrize("suffix", [".jpg", ".jpeg", ".png"])
def test_image_upload_uses_ocr_and_records_extraction_method(tmp_path, monkeypatch, suffix):
    path = tmp_path / f"statement{suffix}"
    Image.new("RGB", (8, 8), "white").save(path)
    monkeypatch.setattr(pytesseract, "image_to_string", lambda image: "Bank statement sample")
    monkeypatch.setattr(pytesseract, "image_to_data", lambda image, output_type: {"conf": [91, -1]})

    extractor = TextExtractor()
    assert extractor.extract(str(path)) == "Bank statement sample"
    assert extractor.last_metadata["method"] == "ocr_image"
    assert extractor.last_metadata["ocr_used"] is True
    assert extractor.last_metadata["ocr_confidence"] == pytest.approx(0.91)
