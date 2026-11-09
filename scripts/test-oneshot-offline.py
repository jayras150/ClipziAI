#!/usr/bin/env python3
"""
Uji mode dispatch ``oneshot`` TANPA menyentuh Vast.ai dan tanpa database.

Semua panggilan SDK dan sesi DB diganti objek palsu, sehingga skrip ini aman
dijalankan di laptop mana pun (tanpa API key, tanpa GPU, tanpa jaringan):

    python scripts/test-oneshot-offline.py

Yang diperiksa:
  1. ``dispatch_mode()`` memilih mode yang benar dari config
  2. perintah onstart valid secara sintaks & memuat task id
  3. pemilihan offer menghormati ``VAST_ONESHOT_MAX_PRICE`` (ambil termurah)
  4. ``_dispatch_oneshot`` mengembalikan instance id & image/env benar
  5. reaper menghapus instance setelah task selesai
  6. reaper tetap menghapus instance walau task ERROR
  7. boot timeout: instance dihapus & task ditandai ERROR
  8. ``cleanup_orphan_instances`` menghapus instance yatim, menyisakan yang aktif

Exit code 0 = semua lulus, 1 = ada yang gagal.
"""
import ast
import asyncio
import os
import pathlib
import re
import sys
import traceback
from uuid import uuid4

BACKEND = pathlib.Path(__file__).resolve().parents[1] / "backend"
if not (BACKEND / "app").is_dir():
    sys.exit(f"folder backend tidak ditemukan di {BACKEND}")
os.chdir(BACKEND)  # app.core.config membaca backend/.env relatif CWD
sys.path.insert(0, str(BACKEND))

from app.services import vast_worker as vw  # noqa: E402

TASK = uuid4()
results: list[tuple[str, bool, str]] = []


# --------------------------------------------------------------------------- #
# Objek palsu (tidak ada panggilan jaringan)
# --------------------------------------------------------------------------- #
class FakeClient:
    def __init__(self, offers):
        self.offers = offers
        self.destroyed: list[int] = []
        self.created: list[tuple] = []
        self.instances: list[dict] = []

    def search_offers(self, *a, **kw):
        return self.offers

    def create_instance(self, offer_id, **kw):
        self.created.append((offer_id, kw))
        return {"success": True, "new_contract": 43832}

    def destroy_instance(self, iid):
        self.destroyed.append(iid)
        return {"success": True}

    def show_instances(self):
        return self.instances


class FakeTask:
    def __init__(self, status_name: str):
        from app.models.task import TaskStatus

        self.status = getattr(TaskStatus, status_name)
        self.error_message = None


class FakeSession:
    def __init__(self, status_name: str):
        self.status_name = status_name

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, model, pk):
        return FakeTask(self.status_name)

    async def commit(self):
        return None


class Row:
    def __init__(self, status):
        self._status = status

    def __getitem__(self, idx):
        return self._status


class Result:
    def __init__(self, statuses):
        self._statuses = statuses

    def all(self):
        return [Row(s) for s in self._statuses]


class OrphanSession(FakeSession):
    """Mengembalikan status task sesuai prefix label instance."""

    def __init__(self, mapping, status_name="COMPLETED"):
        super().__init__(status_name)
        self.mapping = mapping
        self.queried: list[str] = []

    async def execute(self, stmt):
        params = stmt.compile().params
        prefix = str(next(iter(params.values()), "")).rstrip("%")
        self.queried.append(prefix)
        return Result(self.mapping.get(prefix, []))


def check(label: str, fn) -> None:
    try:
        detail = fn()
        results.append((label, True, str(detail)))
    except Exception as exc:  # noqa: BLE001 - laporkan semua kegagalan
        results.append((label, False, f"{type(exc).__name__}: {exc}"))
        traceback.print_exc()


# --------------------------------------------------------------------------- #
# 1. pemilihan mode
# --------------------------------------------------------------------------- #
def test_dispatch_mode():
    original = (vw.settings.VAST_DISPATCH_MODE, vw.settings.VAST_ENDPOINT_URL)
    try:
        vw.settings.VAST_DISPATCH_MODE = "oneshot"
        assert vw.dispatch_mode() == "oneshot", vw.dispatch_mode()
        vw.settings.VAST_DISPATCH_MODE = None
        vw.settings.VAST_ENDPOINT_URL = "https://x.run.vast.ai"
        assert vw.dispatch_mode() == "http", vw.dispatch_mode()
    finally:
        vw.settings.VAST_DISPATCH_MODE, vw.settings.VAST_ENDPOINT_URL = original
    return "oneshot & http terdeteksi"


# --------------------------------------------------------------------------- #
# 2. perintah onstart
# --------------------------------------------------------------------------- #
def test_onstart_command():
    cmd = vw._oneshot_onstart(TASK)
    assert cmd.startswith("cd /app && python -c '"), cmd
    inner = re.search(r"python -c '(.+)'$", cmd)
    assert inner is not None, cmd
    ast.parse(inner.group(1))
    assert str(TASK) in cmd, "task id tidak tertanam di onstart"
    return "sintaks python valid, task id tertanam"


# --------------------------------------------------------------------------- #
# 3. pemilihan offer
# --------------------------------------------------------------------------- #
OFFERS = [
    {"id": 1, "rentable": True, "dph_total": 0.9, "gpu_name": "A"},
    {"id": 2, "rentable": True, "dph_total": 0.3, "gpu_name": "B"},
    {"id": 3, "rentable": False, "dph_total": 0.1, "gpu_name": "C"},
]


def test_pick_offer():
    original = vw.settings.VAST_ONESHOT_MAX_PRICE
    vw.settings.VAST_ONESHOT_MAX_PRICE = 0.5
    try:
        best = asyncio.run(vw._pick_offer(FakeClient(OFFERS)))
    finally:
        vw.settings.VAST_ONESHOT_MAX_PRICE = original
    assert best["id"] == 2, best
    return f"dipilih GPU {best['gpu_name']} ${best['dph_total']}/jam"


# --------------------------------------------------------------------------- #
# 4-5. dispatch + reaper saat task selesai
# --------------------------------------------------------------------------- #
def test_dispatch_and_reaper():
    import app.db.session as dbs

    client = FakeClient(OFFERS)
    vw._get_vast_client = lambda: client
    vw.settings.VAST_ONESHOT_REAP_INTERVAL = 0
    dbs.AsyncSessionLocal = lambda: FakeSession("COMPLETED")

    async def flow():
        result = await vw._dispatch_oneshot(TASK)
        for _ in range(50):  # beri kesempatan reaper berjalan
            await asyncio.sleep(0.02)
        return result

    result = asyncio.run(flow())
    assert result["mode"] == "oneshot", result
    assert result["instance_id"] == 43832, result
    assert client.created[0][0] == 2, client.created
    assert client.created[0][1]["image"], client.created
    assert client.created[0][1]["env"] == {"CLIPZI_ROLE": "worker"}, client.created
    assert client.destroyed == [43832], client.destroyed
    return f"instance {result['instance_id']} dibuat lalu dihapus"


# --------------------------------------------------------------------------- #
# 6. reaper saat task error
# --------------------------------------------------------------------------- #
def test_reaper_on_error():
    import app.db.session as dbs

    client = FakeClient(OFFERS)
    vw._get_vast_client = lambda: client
    dbs.AsyncSessionLocal = lambda: FakeSession("ERROR")
    asyncio.run(vw._reap_instance(111, TASK))
    assert client.destroyed == [111], client.destroyed
    return "instance dihapus walau pipeline gagal"


# --------------------------------------------------------------------------- #
# 7. boot timeout
# --------------------------------------------------------------------------- #
def test_boot_timeout():
    import app.db.session as dbs

    class StuckSession(FakeSession):
        async def get(self, model, pk):
            return FakeTask("QUEUED")

    client = FakeClient(OFFERS)
    vw._get_vast_client = lambda: client
    vw.settings.VAST_ONESHOT_BOOT_TIMEOUT = 0
    dbs.AsyncSessionLocal = lambda: StuckSession("QUEUED")
    asyncio.run(vw._reap_instance(222, TASK))
    assert client.destroyed == [222], client.destroyed
    return "instance dihapus & task ditandai ERROR"


# --------------------------------------------------------------------------- #
# 8. pembersih instance yatim
# --------------------------------------------------------------------------- #
def test_cleanup_orphans():
    import app.db.session as dbs
    import app.models  # noqa: F401 - daftarkan mapper sebelum query
    from app.models.task import TaskStatus

    finished = str(TASK)[:8]
    running = str(uuid4())[:8]

    client = FakeClient([])
    client.instances = [
        {"id": 501, "label": f"clipzi-{finished}"},  # task selesai -> hapus
        {"id": 502, "label": f"clipzi-{running}"},  # task aktif    -> biarkan
        {"id": 503, "label": "clipzi-tidakada"},  # task hilang   -> hapus
        {"id": 504, "label": "server-lain"},  # bukan Clipzi  -> biarkan
    ]
    session = OrphanSession(
        {
            finished: [TaskStatus.COMPLETED],
            running: [TaskStatus.PROCESSING],
        }
    )
    vw._get_vast_client = lambda: client
    dbs.AsyncSessionLocal = lambda: session

    removed = asyncio.run(vw.cleanup_orphan_instances())
    assert removed == 2, (removed, client.destroyed)
    assert sorted(client.destroyed) == [501, 503], client.destroyed
    return f"dihapus {sorted(client.destroyed)}, task aktif dibiarkan"


def test_pyworker_config():
    """Worker Vast wajib memakai PyWorker; port & route-nya harus konsisten."""
    os.environ.setdefault("MODEL_SERVER_PORT", "18000")
    os.environ.setdefault("WORKER_PORT", "8000")
    import importlib

    import deployments.pyworker_main as pw

    pw = importlib.reload(pw)  # baca ulang env yang baru diset
    config = pw.build_config()

    assert config.model_server_port == 18000, config.model_server_port
    assert config.model_server_url == "http://127.0.0.1", config.model_server_url
    routes = [handler.route for handler in config.handlers]
    assert routes == ["/process", "/ping"], routes
    handler = config.handlers[0]
    assert handler.allow_parallel_requests is False, handler
    assert handler.workload_calculator({}) == 100.0, handler.workload_calculator
    # PyWorker menolak start bila tidak ada tepat satu handler ber-BenchmarkConfig.
    benchmarks = [h for h in config.handlers if h.benchmark_config is not None]
    assert len(benchmarks) == 1, benchmarks
    assert benchmarks[0].route == "/ping", benchmarks[0].route
    assert benchmarks[0].benchmark_config.generator() == {}, benchmarks[0]

    # Env yang di instance Vast disediakan otomatis; di sini dummy.
    for name, value in (
        ("CONTAINER_ID", "1"),
        ("REPORT_ADDR", "https://run.vast.ai"),
        ("PUBLIC_IPADDR", "127.0.0.1"),
        ("VAST_TCP_PORT_8000", "8000"),
    ):
        os.environ.setdefault(name, value)

    # Konstruksi Worker = validasi konfigurasi oleh PyWorker itu sendiri.
    # (Tanpa handler ber-BenchmarkConfig, PyWorker langsung melempar exception.)
    from vastai import Worker

    assert Worker(config) is not None

    # PyWorker membaca WORKER_PORT dari environment saat start_server().
    src = pathlib.Path("deployments/pyworker_main.py").read_text(encoding="utf-8")
    assert "WORKER_PORT" in src, "pyworker_main harus menyetel WORKER_PORT"
    entry = pathlib.Path("docker-entrypoint.sh").read_text(encoding="utf-8")
    assert "deployments.pyworker_main" in entry, "entrypoint belum memakai PyWorker"
    assert "CLIPZI_WORKER_MODE" in entry, "mode api tanpa PyWorker harus tersedia"
    return "PyWorker: route /process, model server 127.0.0.1:18000, entrypoint OK"


def test_transcriber_model_choice():
    """Model API (TRANSCRIPTION_MODEL) tidak boleh dipakai faster-whisper lokal."""
    import importlib

    import app.core.config as config_mod

    original = {
        key: os.environ.get(key)
        for key in ("TRANSCRIPTION_PROVIDER", "TRANSCRIPTION_MODEL", "WHISPER_MODEL")
    }
    os.environ["TRANSCRIPTION_PROVIDER"] = "local"
    os.environ["TRANSCRIPTION_MODEL"] = "openai/whisper-large-v3-turbo"
    os.environ["WHISPER_MODEL"] = "small"
    try:
        config_mod.get_settings.cache_clear()
        import app.services.transcriber as transcriber_mod

        transcriber_mod = importlib.reload(transcriber_mod)
        local = transcriber_mod.AudioTranscriber()
        assert local.model_size == "small", local.model_size

        os.environ["TRANSCRIPTION_PROVIDER"] = "groq"
        config_mod.get_settings.cache_clear()
        transcriber_mod = importlib.reload(transcriber_mod)
        remote = transcriber_mod.AudioTranscriber()
        assert remote.model_size == "openai/whisper-large-v3-turbo", remote.model_size
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config_mod.get_settings.cache_clear()
        import app.services.transcriber as transcriber_mod

        importlib.reload(transcriber_mod)
    return "lokal pakai WHISPER_MODEL (small), remote pakai TRANSCRIPTION_MODEL"


def main() -> int:
    # API key wajib ada agar cleanup_orphan_instances mau berjalan.
    if not (vw.settings.VAST_API_KEY or "").strip():
        vw.settings.VAST_API_KEY = "test-key-offline"

    check("dispatch_mode", test_dispatch_mode)
    check("perintah onstart", test_onstart_command)
    check("pemilihan offer", test_pick_offer)
    check("dispatch + reaper selesai", test_dispatch_and_reaper)
    check("reaper saat task ERROR", test_reaper_on_error)
    check("boot timeout", test_boot_timeout)
    check("instance yatim dibersihkan", test_cleanup_orphans)
    check("konfigurasi PyWorker", test_pyworker_config)
    check("model transkripsi per provider", test_transcriber_model_choice)

    print()
    for label, ok, detail in results:
        print(f"{'LULUS' if ok else 'GAGAL'}  {label}: {detail}")

    failed = [r for r in results if not r[1]]
    print()
    if failed:
        print(f"{len(failed)} dari {len(results)} uji GAGAL")
        return 1
    print(f"Semua {len(results)} uji lulus")
    return 0


if __name__ == "__main__":
    sys.exit(main())



