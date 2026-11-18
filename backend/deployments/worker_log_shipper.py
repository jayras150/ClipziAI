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
CALLBACK = (os.environ.get("CLIPZI_CALLBACK_URL") or "").strip()
API = CALLBACK.split("/api/internal/")[0] if CALLBACK else ""
INSTANCE = (os.environ.get("VAST_CONTAINERLABEL") or os.environ.get("CONTAINER_ID") or "").strip()
try:
    INSTANCE_ID = int("" .join(ch for ch in INSTANCE if ch.isdigit()) or 0) or None
except Exception:
    INSTANCE_ID = None
QUEUE_FILE = "/tmp/log_queue.jsonl"
SEQ_LOCK = threading.Lock()
SEQ = {"value": 0}
BUFFER = queue.Queue(maxsize=4000)


def _next_seq():
    with SEQ_LOCK:
        SEQ["value"] += 1
        return SEQ["value"]


def _post(lines):
    if not API or not TOKEN:
        return False
    body = json.dumps({"task_id": TASK_ID or None, "instance_id": INSTANCE_ID, "lines": lines}).encode()
    request = urllib.request.Request(
        API + "/api/internal/worker/logs",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Clipzi-Token": TOKEN},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status < 400
    except Exception:
        return False


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
            lines = [json.loads(row) for row in handle if row.strip()][-400:]
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
    item = {"seq": _next_seq(), "level": level[:16], "stage": (stage or "")[:40], "message": text[:4000]}
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
        emit(line, level="ERROR" if "error" in line.lower() else "INFO", stage=_stage_of(line))
    code = process.wait()
    emit(f"pipeline selesai exit={code} durasi={int(time.time() - started)}s", level="INFO" if code == 0 else "ERROR", stage="exit")
    if code != 0:
        emit("_dmesg: " + _tail("dmesg | tail -40"), level="ERROR", stage="crash")
        emit("_nvidia_smi: " + _tail("nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv"), level="ERROR", stage="crash")
    time.sleep(3)
    _drain_persisted()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
