"""Unit test validasi model Whisper CT2 (tanpa koneksi Drive/DB)."""
import json

import pytest
from fastapi import HTTPException

from app.api.admin.whisper_models import (
    COLAB_NOTEBOOK_PATH,
    _extract_drive_id,
)
from app.services.whisper_model_manager import inspect_files, normalize_slug



def _file(name: str, size: int = 1024) -> dict:
    return {"name": name, "size": str(size), "mimeType": "application/octet-stream"}


def test_valid_ct2_folder():
    result = inspect_files(
        [
            _file("model.bin", 3_000_000_000),
            _file("config.json"),
            _file("tokenizer.json"),
            _file("preprocessor_config.json"),
            _file("vocabulary.json"),
        ]
    )
    assert result["status"] == "available"
    assert result["size_bytes"] == 3_000_004_096
    assert result["file_count"] == 5
    assert result["validation_error"] is None


def test_empty_folder_is_missing():
    result = inspect_files([])
    assert result["status"] == "missing"
    assert "kosong" in result["validation_error"].lower()


def test_incomplete_ct2_is_invalid():
    result = inspect_files(
        [
            _file("model.bin"),
            _file("config.json"),
            _file("tokenizer.json"),
        ]
    )
    assert result["status"] == "invalid"
    assert "preprocessor_config.json" in result["validation_error"]


def test_pytorch_is_rejected_with_conversion_hint():
    result = inspect_files(
        [
            _file("model.safetensors"),
            _file("config.json"),
            _file("tokenizer.json"),
            _file("preprocessor_config.json"),
            _file("vocabulary.json"),
        ]
    )
    assert result["status"] == "invalid"
    assert "PyTorch" in result["validation_error"]
    assert "CT2" in result["validation_error"]


def test_tensorflow_is_rejected():
    result = inspect_files(
        [
            _file("tf_model.h5"),
            _file("config.json"),
            _file("tokenizer.json"),
            _file("preprocessor_config.json"),
            _file("vocabulary.json"),
        ]
    )
    assert result["status"] == "invalid"
    assert "TensorFlow" in result["validation_error"]


def test_vocabulary_optional_spelling():
    result = inspect_files(
        [
            _file("model.bin"),
            _file("config.json"),
            _file("tokenizer.json"),
            _file("preprocessor_config.json"),
            _file("vocabulary.txt"),
        ]
    )
    assert result["status"] == "available"


def test_extract_drive_id_from_url_and_raw():
    raw = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
    assert _extract_drive_id(raw) == raw
    assert _extract_drive_id(f"https://drive.google.com/file/d/{raw}/view") == raw
    assert _extract_drive_id(f"https://drive.google.com/open?id={raw}") == raw


def test_extract_drive_id_rejects_invalid():
    with pytest.raises(HTTPException) as excinfo:
        _extract_drive_id("bukan-id")
    assert excinfo.value.status_code == 400


def test_normalize_slug():
    assert normalize_slug("Large V3 / Turbo") == "large-v3-turbo"
    assert normalize_slug("  ") == ""


def test_colab_notebook_template_valid():
    assert COLAB_NOTEBOOK_PATH.is_file()
    data = json.loads(COLAB_NOTEBOOK_PATH.read_text(encoding="utf-8"))
    assert data["nbformat"] == 4
    code_cells = [cell for cell in data["cells"] if cell["cell_type"] == "code"]
    assert len(code_cells) >= 5
    source = "\n".join(cell["source"] for cell in code_cells)
    assert "1H8eharRd98Poq8e2qYEkq9UYiOaPTNR4" in source
    assert "auth.authenticate_user()" in source
    assert "MediaFileUpload" in source

