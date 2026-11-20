#!/usr/bin/env python3
"""Shipper log worker: kirim stdout/stderr + ringkasan crash ke backend.

Dipakai onstart:  python worker_log_shipper.py -- <perintah pipeline>
Log dikirim ke POST /api/internal/worker/logs (header X-Clipzi-Token),
batch tiap 2 detik / 60 baris, retry backoff, antrean disimpan di /tmp.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

TOKEN = (os.environ.get("CLIPZI_WORKER_TOKEN") or "").strip()
TASK_ID = (os.environ.get("CLIPZI_TASK_ID") or "").strip()
# Cloudflare memblokir User-Agent default urllib ("Python-urllib/3.11") dengan
# error 1010 / HTTP 403. Tanpa UA sendiri, SEMUA log pipeline ditolak dan hanya
# tersimpan di /tmp (hilang saat instance dihapus) — itulah sebabnya admin
# hanya melihat log boot dari onstart_log.py.
USER_AGENT = "ClipziAI-Worker/1.0"
CALLBACK = (os.environ.get("CLIPZI_CALLBACK_URL") or "").strip()
API = (os.environ.get("CLIPZI_API_BASE") or (CALLBACK.split("/api/internal/")[0] if CALLBACK else "")).rstrip("/")
INSTANCE = (os.environ.get("VAST_CONTAINERLABEL") or os.environ.get("CONTAINER_ID") or "").strip()
try:
    INSTANCE_ID = int("" .join(ch for ch in INSTANCE if ch.isdigit()) or 0) or None
except Exception:
    INSTANCE_ID = None
QUEUE_FILE = "/tmp/log_queue.jsonl"
SEQ_LOCK = threading.Lock()
# Pre-log onstart (deployments/onstart_log.py) memakai seq 1..N SEBELUM pipeline
# jalan. Shipper harus melanjutkan dari offset itu, kalau tidak barisnya
# bertabrakan di unique index (task_id, seq) dan log onstart hilang.
try:
    _SEQ_START = int(os.environ.get("CLIPZI_LOG_SEQ_OFFSET") or 0)
except (TypeError, ValueError):
    _SEQ_START = 0
SEQ = {"value": _SEQ_START}
BUFFER = queue.Queue(maxsize=4000)


def _next_seq():
    with SEQ_LOCK:
        SEQ["value"] += 1
        return SEQ["value"]


def _post(lines):
    if not API or not TOKEN or not lines:
        return False
    body = json.dumps({"task_id": TASK_ID or None, "instance_id": INSTANCE_ID, "lines": lines}).encode()
    # Retry 3x: instance bisa dihapus beberapa detik setelah pipeline gagal,
    # jadi satu kegagalan kecil pun membuat log terakhir hilang selamanya.
    for attempt in range(3):
        request = urllib.request.Request(
            API + "/api/internal/worker/logs",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Clipzi-Token": TOKEN,
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status < 400:
                    return True
        except Exception:
            pass
        time.sleep(0.4 * (attempt + 1))
    return False


def _flush_now():
    """Kirim semua yang ada di buffer SEKARANG (dipakai saat ada ERROR/exit)."""
    items = []
    while True:
        try:
            items.append(BUFFER.get_nowait())
        except queue.Empty:
            break
    if not items:
        return True
    if not _post(items):
        _persist(items)
        return False
    return True


def _persist(lines):
    try:
        with open(QUEUE_FILE, "a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(json.dumps(line) + "\n")
    except OSError:
        pass


def _drain_persisted():
    try:
        if not os.path.exists(QUEUE_FILE) or os.path.getsize(QUEUE_FILE) == 0:
            return
        with open(QUEUE_FILE, "r", encoding="utf-8") as handle:
            lines = [json.loads(row) for row in handle if row.strip()][-2000:]
        if lines and _post(lines):
            open(QUEUE_FILE, "w").close()
    except Exception:
        pass


def shipper_loop():
    batch, last_flush = [], time.time()
    while True:
        try:
            item = BUFFER.get(timeout=1.0)
            batch.append(item)
        except queue.Empty:
            pass
        if batch and (len(batch) >= 60 or time.time() - last_flush >= 2):
            _drain_persisted()
            if not _post(batch):
                _persist(batch)
            batch, last_flush = [], time.time()


def emit(message, level="INFO", stage=None):
    text = str(message or "").rstrip("\n")
    if not text:
        return
    # 20000 char: satu traceback SSL/boto3 bisa >4000 char. Dulu dipotong 4000
    # sehingga error di admin berhenti di tengah URL dan tidak bisa didiagnosis.
    item = {"seq": _next_seq(), "level": level[:16], "stage": (stage or "")[:40], "message": text[:20000]}
    try:
        BUFFER.put_nowait(item)
    except queue.Full:
        _persist([item])


def _stage_of(line):
    lowered = line.lower()
    for token, stage in (
        ("transcrib", "transcribe"), ("whisper", "transcribe"), ("download", "download"),
        ("render", "render"), ("ffmpeg", "render"), ("upload", "upload"), ("metadata", "metadata"),
        ("plan", "plan"), ("clip", "plan"),
    ):
        if token in lowered:
            return stage
    return None


def _tail(command):
    try:
        out = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
        return (out.stdout or "")[-1200:]
    except Exception:
        return ""


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    threading.Thread(target=shipper_loop, daemon=True).start()
    emit("shipper aktif: log instance akan dikirim ke backend", stage="boot")
    started = time.time()
    try:
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except Exception as exc:
        emit(f"gagal menjalankan pipeline: {exc}", level="ERROR", stage="boot")
        return 1
    for line in process.stdout or []:
        sys.stdout.write(line)
        level = "ERROR" if "error" in line.lower() else "INFO"
        emit(line, level=level, stage=_stage_of(line))
        if level == "ERROR":
            # Jangan menunggu batch 2 detik: instance sering dihapus tepat
            # setelah pipeline gagal, sehingga batch terakhir hilang.
            _flush_now()
    code = process.wait()
    emit(f"pipeline selesai exit={code} durasi={int(time.time() - started)}s", level="INFO" if code == 0 else "ERROR", stage="exit")
    if code != 0:
        emit("_dmesg: " + _tail("dmesg | tail -40"), level="ERROR", stage="crash")
        emit("_nvidia_smi: " + _tail("nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv"), level="ERROR", stage="crash")
    # Kirim sisa buffer + antrean persist sebelum container dimatikan reaper.
    for _ in range(8):
        _flush_now()
        _drain_persisted()
        if BUFFER.empty():
            break
        time.sleep(1)
    time.sleep(2)
    _flush_now()
    _drain_persisted()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
