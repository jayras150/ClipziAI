"""Regression test GPU probe: perilaku nyata, bukan sekadar keberadaan fungsi."""
import time

from app.services.local_llm import (
    LocalLLM,
    cuda_fallback_reason,
    parse_cuda_device_count,
    parse_offload,
)

CUDA_LOG = """
ggml_cuda_init: found 1 CUDA devices:
  Device 0: NVIDIA GeForce RTX 3060, compute capability 8.6
load_tensors: offloaded 33/33 layers to GPU
llama_model_load: model size = 2400 MiB
"""

CPU_LOG = """
warning: no usable GPU found, --gpu-layers option will be ignored
warning: one possible reason is that llama.cpp was compiled without GPU support
"""


def _llm(tmp_path, log_text, used_mb):
    llm = LocalLLM()
    path = tmp_path / "llama.log"
    path.write_text(log_text, encoding="utf-8")
    llm._log_path = str(path)
    llm.devices = ["CUDA0: NVIDIA GeForce RTX 3060 (12288 MiB, 12000 MiB free)"]
    smi = {"name": "NVIDIA GeForce RTX 3060", "total_mb": 12288, "used_mb": used_mb}
    llm._nvidia_smi = lambda: dict(smi)
    return llm


def test_parse_offload_dan_device_count():
    assert parse_offload(CUDA_LOG) == (33, 33, "GPU")
    assert parse_offload("offloaded 20/33 layers to CUDA0") == (20, 33, "CUDA0")
    assert parse_offload("tidak ada baris offload") == (0, 0, "")
    assert parse_cuda_device_count(CUDA_LOG) == 1
    assert parse_cuda_device_count(CPU_LOG) == 0


def test_alasan_fallback_cpu_dari_log_produksi():
    reason = cuda_fallback_reason(CPU_LOG)
    assert "no usable GPU found" in reason
    assert cuda_fallback_reason(CUDA_LOG) == ""


def test_probe_lulus_saat_semua_layer_offload(tmp_path):
    llm = _llm(tmp_path, CUDA_LOG, used_mb=2900)
    probe = llm.gpu_probe(vram_before_mb=116, wait_seconds=0)
    assert probe["ok"] is True, probe["reason"]
    assert probe["offloaded"] == 33 and probe["layers"] == 33
    assert probe["vram_delta_mb"] == 2784
    assert probe["cuda_devices"] == 1


def test_probe_gagal_saat_log_masih_cpu_walau_device_terlihat(tmp_path):
    llm = _llm(tmp_path, CPU_LOG, used_mb=120)
    probe = llm.gpu_probe(vram_before_mb=116, wait_seconds=0)
    assert probe["ok"] is False
    assert "no usable GPU found" in probe["reason"]


def test_probe_gagal_saat_offload_hanya_sebagian(tmp_path):
    log = "load_tensors: offloaded 5/33 layers to GPU" + chr(10)
    llm = _llm(tmp_path, log, used_mb=2900)
    probe = llm.gpu_probe(vram_before_mb=116, wait_seconds=0)
    assert probe["ok"] is False
    assert "5/33" in probe["reason"]


def test_probe_gagal_saat_vram_tidak_naik_signifikan(tmp_path):
    llm = _llm(tmp_path, CUDA_LOG, used_mb=180)
    probe = llm.gpu_probe(vram_before_mb=116, wait_seconds=0)
    assert probe["ok"] is False
    assert "VRAM" in probe["reason"]


def test_start_tidak_menjalankan_cpu_saat_gpu_wajib(tmp_path, monkeypatch):
    llm = LocalLLM()
    monkeypatch.setattr(LocalLLM, "available", property(lambda self: True))
    llm._log_path = str(tmp_path / "llama.log")
    monkeypatch.setattr(llm, "_detect_devices", lambda: [])
    monkeypatch.setattr(llm, "_healthy", lambda: False)
    assert llm.start() is False
    assert "CUDA" in llm.last_error
    assert llm.process is None


def test_chat_tidak_memanggil_server_saat_deadline_habis(monkeypatch):
    llm = LocalLLM()
    monkeypatch.setattr(llm, "start", lambda: True)
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        raise AssertionError("httpx.post tidak boleh dipanggil")

    monkeypatch.setattr("app.services.local_llm.httpx.post", fake_post)
    assert llm.chat("sistem", "user", deadline=time.monotonic() - 1) is None
    assert calls == []


def test_chat_memakai_sisa_deadline_sebagai_read_timeout(tmp_path, monkeypatch):
    llm = LocalLLM()
    llm._log_path = str(tmp_path / "llama.log")
    monkeypatch.setattr(llm, "start", lambda: True)
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "OK"}}]}

    def fake_post(url, json=None, timeout=None):
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("app.services.local_llm.httpx.post", fake_post)
    deadline = time.monotonic() + 30
    result = llm.chat("sistem", "user", deadline=deadline)
    assert result == "OK"
    assert 5.0 <= captured["timeout"].read <= 30.5


def test_log_lama_tidak_membuat_probe_lulus(tmp_path):
    # Skenario: run sebelumnya sukses CUDA, run sekarang jatuh ke CPU.
    llm = _llm(tmp_path, CUDA_LOG, used_mb=120)
    llm.log_mark = len(CUDA_LOG)
    with open(llm._log_path, "a", encoding="utf-8") as handle:
        handle.write(CPU_LOG)
    probe = llm.gpu_probe(vram_before_mb=116, wait_seconds=0)
    assert probe["ok"] is False
    assert "no usable GPU found" in probe["reason"]
