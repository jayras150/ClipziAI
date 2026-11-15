#!/usr/bin/env python3
"""Downloader/konverter model Whisper untuk Clipzi AI (Google Colab).

Script ini menerima model HuggingFace **PyTorch** atau **CT2**, lalu selalu
menghasilkan folder CT2 yang kompatibel dengan faster-whisper. Hasilnya diunggah
ke folder Google Drive yang dibaca backend (service account) dan dipakai Vast
Cloud Sync saat instance worker dibuat.

Contoh di Colab:

    !python colab_whisper_export.py \
        --repo openai/whisper-large-v3-turbo \
        --slug large-v3-turbo

Untuk model CT2 yang sudah siap:

    !python colab_whisper_export.py \
        --repo Systran/faster-whisper-large-v3 \
        --slug large-v3

Catatan:
- Upload memakai akun Google Anda (mount Drive), bukan service account, karena
  service account tidak punya kuota Drive.
- TensorFlow tidak didukung dan akan ditolak.
- Script menulis folder model langsung (bukan ZIP) supaya `cloud_copy` Vast
  bisa menyalin isi folder ke `/workspace/whisper_model`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

CT2_REQUIRED = ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json")
CT2_VOCAB = ("vocabulary.json", "vocabulary.txt")
PYTORCH_MARKERS = ("model.safetensors", "pytorch_model.bin")
TENSORFLOW_MARKERS = ("tf_model.h5", "model.ckpt.index")
COPY_EXTRA = ("tokenizer.json", "preprocessor_config.json", "vocabulary.json", "vocabulary.txt")
DEFAULT_DRIVE_ROOT = "/content/drive/MyDrive/vast-backup/Clipzy/whisper_models"


def file_names(folder: Path) -> set[str]:
    if not folder.is_dir():
        return set()
    return {item.name.lower() for item in folder.iterdir() if item.is_file()}


def folder_size(folder: Path) -> int:
    total = 0
    for item in folder.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def classify(folder: Path) -> str:
    names = file_names(folder)
    if any(marker in names for marker in TENSORFLOW_MARKERS):
        return "tensorflow"
    if "model.bin" in names:
        return "ct2"
    if any(marker in names for marker in PYTORCH_MARKERS):
        return "pytorch"
    return "unknown"


def validate_ct2(folder: Path) -> List[str]:
    names = file_names(folder)
    missing = [name for name in CT2_REQUIRED if name not in names]
    if not any(name in names for name in CT2_VOCAB):
        missing.append("vocabulary.json/vocabulary.txt")
    return missing

def download_model(repo: str, source: Path) -> None:
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True, exist_ok=True)
    local = Path(repo).expanduser()
    if local.is_dir():
        print(f"[src] menyalin folder lokal {local}")
        shutil.copytree(local, source, dirs_exist_ok=True, symlinks=False)
        return
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - Colab
        raise SystemExit("huggingface_hub belum terpasang. Jalankan: pip install -q huggingface_hub") from exc
    print(f"[src] mengunduh {repo} ...")
    snapshot_download(
        repo_id=repo,
        local_dir=str(source),
        local_dir_use_symlinks=False,
        resume_download=True,
    )


def convert_to_ct2(source: Path, output: Path, quantization: str) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    converter = shutil.which("ct2-transformers-converter")
    if converter:
        command = [
            converter,
            "--model",
            str(source),
            "--output_dir",
            str(output),
            "--quantization",
            quantization,
        ]
    else:
        command = [
            sys.executable,
            "-m",
            "ctranslate2.converters.transformers",
            "--model",
            str(source),
            "--output_dir",
            str(output),
            "--quantization",
            quantization,
        ]
    print("[convert] " + " ".join(command))
    subprocess.run(command, check=True)
    for name in COPY_EXTRA:
        candidate = source / name
        if candidate.exists() and not (output / name).exists():
            shutil.copy2(candidate, output / name)


def prepare_ct2(repo: str, work_dir: Path, quantization: str) -> tuple[Path, str]:
    source = work_dir / "source"
    download_model(repo, source)
    kind = classify(source)
    print(f"[detect] jenis model: {kind}")
    if kind == "tensorflow":
        raise SystemExit("Model TensorFlow tidak didukung. Gunakan repo PyTorch atau CT2.")
    if kind == "ct2":
        missing = validate_ct2(source)
        if missing:
            raise SystemExit("Model CT2 tidak lengkap: " + ", ".join(missing))
        return source, "ct2"
    if kind == "pytorch":
        output = work_dir / "ct2"
        convert_to_ct2(source, output, quantization)
        missing = validate_ct2(output)
        if missing:
            raise SystemExit("Hasil konversi CT2 tidak lengkap: " + ", ".join(missing))
        return output, "pytorch->ct2"
    raise SystemExit("Tidak mengenali model: tidak ada model.bin/safetensors/pytorch_model.bin.")

def mount_drive() -> None:
    try:
        from google.colab import drive  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Mount Drive hanya tersedia di Colab. Jalankan dengan --no-mount "
            "dan --drive-root lokal untuk uji."
        ) from exc
    drive.mount("/content/drive")


def upload_to_drive(source: Path, drive_root: Path, slug: str, overwrite: bool, manifest: Dict[str, Any]) -> Path:
    destination = drive_root / slug
    if destination.exists():
        if not overwrite:
            raise SystemExit(
                f"Folder tujuan sudah ada: {destination}. Pakai --overwrite untuk mengganti."
            )
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.is_file() and not item.name.startswith("."):
            shutil.copy2(item, destination / item.name)
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Ekspor model Whisper ke CT2 + Google Drive")
    parser.add_argument("--repo", default="Systran/faster-whisper-large-v3")
    parser.add_argument("--slug", default="")
    parser.add_argument("--quantization", default="float16", choices=["float16", "int8", "int8_float16"])
    parser.add_argument("--drive-root", default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--work-dir", default="/content/whisper_model_work")
    parser.add_argument("--no-mount", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    slug = args.slug.strip() or args.repo.rstrip("/").split("/")[-1]
    work_dir = Path(args.work_dir).expanduser()
    work_dir.mkdir(parents=True, exist_ok=True)
    ct2_dir, source_kind = prepare_ct2(args.repo, work_dir, args.quantization)
    missing = validate_ct2(ct2_dir)
    if missing:
        raise SystemExit("CT2 belum valid: " + ", ".join(missing))

    size = folder_size(ct2_dir)
    print(f"[ok] CT2 siap: {ct2_dir} ({size / 1024**3:.2f} GiB)")
    if not args.no_mount:
        mount_drive()
    drive_root = Path(args.drive_root).expanduser()
    drive_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source_repo": args.repo,
        "source_kind": source_kind,
        "quantization": args.quantization,
        "slug": slug,
        "size_bytes": size,
        "files": sorted(item.name for item in ct2_dir.iterdir() if item.is_file()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": "Upload oleh akun Google pemilik Drive; service account hanya membaca/menghapus.",
    }
    destination = upload_to_drive(ct2_dir, drive_root, slug, args.overwrite, manifest)
    print(f"[drive] selesai: {destination}")
    print("[next] Buka admin → Settings → Whisper Models → Scan Drive → Aktifkan.")


if __name__ == "__main__":
    main()


