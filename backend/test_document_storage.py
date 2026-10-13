import hashlib
from pathlib import Path

from database.crud import save_document


class _CaptureSession:
    def __init__(self):
        self.added = None

    def add(self, value):
        self.added = value

    def commit(self):
        pass

    def refresh(self, value):
        pass


def test_uploaded_document_is_copied_to_application_scoped_durable_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("PRISM_DOCUMENT_STORAGE_ROOT", str(tmp_path / "documents"))
    upload = tmp_path / "source.pdf"
    contents = b"synthetic evidence bytes"
    upload.write_bytes(contents)
    session = _CaptureSession()

    record = save_document(session, 742, "BANK_STATEMENT", "statement.pdf", str(upload))

    stored = Path(record.storage_path)
    assert record is session.added
    assert stored.exists()
    assert stored.read_bytes() == contents
    assert record.document_hash == hashlib.sha256(contents).hexdigest()
    assert record.processing_status == "UPLOADED"
    assert record.application_id == 742
    assert stored.parent == tmp_path / "documents" / "application_742"
