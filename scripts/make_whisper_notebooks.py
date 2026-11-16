"""Generator notebook Colab Whisper untuk semua provider.

Jalankan: python scripts/make_whisper_notebooks.py
Output: backend/app/templates/whisper_colab_<provider>.ipynb
"""
from __future__ import annotations

import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "backend" / "app" / "templates"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(True)}


def code(text: str, meta: dict | None = None) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"cellView": "form", **(meta or {})},
        "outputs": [],
        "source": text.splitlines(True),
    }


INTRO = """# Clipzi AI — Whisper model → {label}

Notebook ini **self-contained**: tidak perlu clone repo Clipzi yang private.

1. Isi kredensial {label} di sel konfigurasi (atau tempel saat diminta).
2. Klik **Runtime → Run all**.
3. Setelah selesai, kembali ke admin **Settings → Models**, pilih provider
   **{label}**, lalu tekan **Scan** dan **Aktifkan** model.

Upload memakai kuota/akun {label} milik Anda sendiri.
"""

PIP = """import subprocess
import sys

subprocess.check_call(
    [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-q",
        "faster-whisper",
        "ctranslate2",
        "transformers",
        "huggingface_hub",
        "tqdm",
        "{extra}",
    ]
)
"""

CONFIG = '''# @title Konfigurasi model {{ display-mode: "form" }}
MODEL_REPO = "{repo}"  # @param ["Systran/faster-whisper-large-v3", "Systran/faster-whisper-large-v3-turbo", "Systran/faster-whisper-medium", "Systran/faster-whisper-small", "openai/whisper-large-v3"]
SLUG = "{slug}"  # @param {{type:"string"}}
QUANTIZATION = "float16"  # @param ["float16", "int8", "int8_float16"]
OVERWRITE = False  # @param {{type:"boolean"}}
RESUME = True  # @param {{type:"boolean"}}

{extra_config}
'''

DOWNLOAD = """import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

WORK = Path("/content/clipzi_model")
SOURCE = WORK / "source"
CT2_DIR = WORK / "ct2"
MODEL_DIR = WORK / "upload"

if WORK.exists():
    shutil.rmtree(WORK)
SOURCE.mkdir(parents=True, exist_ok=True)

print("Mengunduh:", MODEL_REPO)
snapshot_download(repo_id=MODEL_REPO, local_dir=str(SOURCE))
print("Download selesai:", SOURCE)
"""

VALIDATE = '''import shutil
import subprocess
import sys
from pathlib import Path

REQUIRED = ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json")
VOCAB = ("vocabulary.json", "vocabulary.txt")
PYTORCH = ("model.safetensors", "pytorch_model.bin")


def names(path: Path) -> set[str]:
    return {item.name.lower() for item in path.iterdir() if item.is_file()}


found = names(SOURCE)
print("File HF:", sorted(found)[:12])

if "model.bin" in found:
    TARGET = SOURCE
else:
    if not any(marker in found for marker in PYTORCH):
        raise SystemExit(
            "Repo tidak berisi model.bin (CT2) maupun bobot PyTorch. "
            "Pakai repo Systran/faster-whisper-* atau openai/whisper-*."
        )
    print("Konversi PyTorch -> CTranslate2 (float16)…")
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "ctranslate2.converters.transformers",
            "--model",
            str(SOURCE),
            "--quantization",
            QUANTIZATION,
            "--output_dir",
            str(CT2_DIR),
        ]
    )
    TARGET = CT2_DIR

present = names(TARGET)
missing = [name for name in REQUIRED if name not in present]
if missing:
    raise SystemExit(f"Model CT2 tidak lengkap, kurang: {missing}")
if not any(name in present for name in VOCAB):
    raise SystemExit("Model CT2 tidak punya vocabulary.json/vocabulary.txt.")

size = sum(item.stat().st_size for item in TARGET.iterdir() if item.is_file())
print(f"Model siap: {TARGET} ({size / (1024**3):.2f} GiB)")
'''

DROPBOX_AUTH = '''from getpass import getpass

import dropbox

APP_KEY = getpass("Dropbox App key: ")
APP_SECRET = getpass("Dropbox App secret: ")

flow = dropbox.DropboxOAuth2FlowNoRedirect(
    APP_KEY, APP_SECRET, token_access_type="offline"
)
print("Buka URL berikut, izinkan akses, lalu tempel kodenya:")
print(flow.start())
auth_code = input("Kode otorisasi: ").strip()
result = flow.finish(auth_code)
print("REFRESH TOKEN (simpan di admin Clipzi):", result.refresh_token)

dbx = dropbox.Dropbox(
    oauth2_refresh_token=result.refresh_token, app_key=APP_KEY, app_secret=APP_SECRET
)
print("Terhubung sebagai:", dbx.users_get_current_account().email)
'''

DROPBOX_UPLOAD = '''from pathlib import Path

import dropbox

ROOT = DROPBOX_ROOT.rstrip("/")
DEST = f"{ROOT}/{SLUG}"
try:
    dbx.files_create_folder_v2(DEST)
except Exception as exc:  # folder sudah ada
    if "conflict" not in str(exc).lower():
        raise

CHUNK = int(CHUNK_MB) * 1024 * 1024
for path in sorted(TARGET.iterdir()):
    if not path.is_file():
        continue
    target = f"{DEST}/{path.name}"
    size = path.stat().st_size
    if not OVERWRITE:
        try:
            meta = dbx.files_get_metadata(target)
            if getattr(meta, "size", None) == size:
                print("skip (sudah sama):", target)
                continue
        except Exception:
            pass
    print(f"upload {path.name} ({size / 1048576:.1f} MiB)")
    if size <= CHUNK:
        with open(path, "rb") as handle:
            dbx.files_upload(
                handle.read(), target, mode=dropbox.files.WriteMode.overwrite
            )
        continue
    with open(path, "rb") as handle:
        session = dbx.files_upload_session_start(handle.read(CHUNK))
        cursor = dropbox.files.UploadSessionCursor(
            session_id=session.session_id, offset=handle.tell()
        )
        while handle.tell() < size:
            if size - handle.tell() <= CHUNK:
                commit = dropbox.files.CommitInfo(
                    path=target, mode=dropbox.files.WriteMode.overwrite
                )
                dbx.files_upload_session_finish(handle.read(CHUNK), cursor, commit)
                break
            dbx.files_upload_session_append_v2(handle.read(CHUNK), cursor)
            cursor.offset = handle.tell()
print("Selesai:", DEST)
'''

S3_AUTH = '''from getpass import getpass

import boto3
from botocore.config import Config

ACCESS_KEY = getpass("Access key ID: ")
SECRET_KEY = getpass("Secret access key: ")

client = boto3.client(
    "s3",
    endpoint_url=ENDPOINT or None,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    region_name=REGION,
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "path" if PATH_STYLE else "auto"},
    ),
)
client.head_bucket(Bucket=BUCKET)
print("Bucket siap:", BUCKET)
'''

S3_UPLOAD = '''import boto3
from botocore.config import Config
from pathlib import Path

client = boto3.client(
    "s3",
    endpoint_url=ENDPOINT or None,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    region_name=REGION,
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "path" if PATH_STYLE else "auto"},
    ),
)

prefix = f"{BUCKET_ROOT.strip('/')}/{SLUG}" if BUCKET_ROOT.strip("/") else SLUG
for path in sorted(TARGET.iterdir()):
    if not path.is_file():
        continue
    key = f"{prefix}/{path.name}"
    print("upload", key)
    client.upload_file(
        str(path),
        BUCKET,
        key,
        ExtraArgs={"ContentType": "application/octet-stream"},
    )
print(f"Selesai: s3://{BUCKET}/{prefix}")
'''

HF_AUTH = '''from getpass import getpass

from huggingface_hub import HfApi

HF_TOKEN = getpass("Hugging Face token (kosongkan bila repo publik): ")
api = HfApi(token=HF_TOKEN or None)
info = api.model_info(MODEL_REPO)
print("Repo:", info.id, "| private:", getattr(info, "private", False))
'''

HF_UPLOAD = '''from huggingface_hub import HfApi

api = HfApi(token=HF_TOKEN or None)
files = api.list_repo_files(MODEL_REPO)
required = ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json")
missing = [name for name in required if name not in files]
if missing:
    raise SystemExit(
        f"Repo {MODEL_REPO} bukan CT2 lengkap; kurang: {missing}. "
        "Pakai repo Systran/faster-whisper-*."
    )
print("Repo CT2 siap dipakai worker:", MODEL_REPO)
print("Di admin Clipzi: pilih provider Hugging Face, isi repo id, lalu Scan + Aktifkan.")
'''


def s3_config(endpoint: str, bucket: str, region: str, path_style: bool) -> str:
    style = "True" if path_style else "False"
    return (
        f'ENDPOINT = "{endpoint}"  # @param {{type:"string"}}\n'
        f'BUCKET = "{bucket}"  # @param {{type:"string"}}\n'
        f'REGION = "{region}"  # @param {{type:"string"}}\n'
        'BUCKET_ROOT = "whisper_models"  # @param {type:"string"}\n'
        f'PATH_STYLE = {style}  # @param {{type:"boolean"}}\n'
    )


PROVIDERS = {
    "dropbox": {
        "label": "Dropbox",
        "repo": "Systran/faster-whisper-large-v3",
        "slug": "large-v3",
        "pip": "dropbox",
        "config": (
            'DROPBOX_ROOT = "/Clipzy/whisper_models"  # @param {type:"string"}\n'
            'CHUNK_MB = 8  # @param {type:"integer"}\n'
        ),
        "auth": DROPBOX_AUTH,
        "upload": DROPBOX_UPLOAD,
    },
    "backblaze": {
        "label": "Backblaze B2",
        "repo": "Systran/faster-whisper-large-v3",
        "slug": "large-v3",
        "pip": "boto3",
        "config": s3_config("https://s3.us-west-004.backblazeb2.com", "", "us-west-004", True),
        "auth": S3_AUTH,
        "upload": S3_UPLOAD,
    },
    "s3": {
        "label": "Amazon S3",
        "repo": "Systran/faster-whisper-large-v3",
        "slug": "large-v3",
        "pip": "boto3",
        "config": s3_config("", "", "us-east-1", False),
        "auth": S3_AUTH,
        "upload": S3_UPLOAD,
    },
    "huggingface": {
        "label": "Hugging Face",
        "repo": "Systran/faster-whisper-large-v3",
        "slug": "large-v3",
        "pip": "",
        "config": "",
        "auth": HF_AUTH,
        "upload": HF_UPLOAD,
    },
}


def build(provider_id: str) -> dict:
    spec = PROVIDERS[provider_id]
    cells = [
        md(INTRO.format(label=spec["label"])),
        code(
            CONFIG.format(
                repo=spec["repo"], slug=spec["slug"], extra_config=spec["config"]
            )
        ),
        code(PIP.format(extra=spec["pip"])),
        code(spec["auth"]),
        code(DOWNLOAD),
        code(VALIDATE),
        code(spec["upload"]),
    ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.11"},
            "colab": {"provenance": []},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for provider_id in PROVIDERS:
        path = OUT_DIR / f"whisper_colab_{provider_id}.ipynb"
        path.write_text(
            json.dumps(build(provider_id), indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("wrote", path.name)


if __name__ == "__main__":
    main()
