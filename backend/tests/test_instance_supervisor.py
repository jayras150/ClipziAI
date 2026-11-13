"""Unit test supervisor instance Vast (tanpa DB & tanpa Vast API asli)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from app.services import instance_supervisor as module
from app.services.instance_supervisor import InstanceSupervisor


_DEFAULT_INFO = {"actual_status": "running", "status_msg": "success"}
_MISSING = object()


class _FakeClient:
    def __init__(
        self,
        sequence: List[Optional[Dict[str, Any]]],
        default: Any = _MISSING,
        existing_ids: Optional[List[int]] = None,
    ) -> None:
        self.sequence = list(sequence)
        self.default = _DEFAULT_INFO if default is _MISSING else default
        self.destroyed: List[int] = []
        self.existing_ids = [1] if existing_ids is None else existing_ids

    def show_instance(self, instance_id: int) -> Optional[Dict[str, Any]]:
        if not self.sequence:
            return self.default
        item = self.sequence.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def show_instances(self) -> List[Dict[str, Any]]:
        return [{"id": i, "actual_status": "running"} for i in self.existing_ids]

    def destroy_instance(self, instance_id: int) -> Dict[str, Any]:
        self.destroyed.append(instance_id)
        return {"success": True}

    def logs(self, instance_id: int, tail: str = "200") -> str:
        return "log line"


def _supervisor(
    client: _FakeClient,
    status_sequence: List[str],
    offers: Optional[List[Dict[str, Any]]] = None,
    create_ids: Optional[List[int]] = None,
) -> InstanceSupervisor:
    statuses = list(status_sequence)
    ids = list(create_ids or [1])
    offers = offers or [
        {"id": 10, "machine_id": 1, "gpu_name": "RTX 4090", "dph_total": 0.2}
    ]

    async def pick_offer(_client: Any, exclude_machines=None, price_ceiling=0.0):
        return offers.pop(0) if len(offers) > 1 else offers[0]

    async def create_instance(offer: Dict[str, Any]) -> int:
        return ids.pop(0) if len(ids) > 1 else ids[0]

    sup = InstanceSupervisor(
        client=client,
        task_id="00000000-0000-0000-0000-000000000001",
        offer=offers[0],
        pick_offer=pick_offer,
        create_instance=create_instance,
    )

    async def task_status() -> Optional[str]:
        return statuses.pop(0) if len(statuses) > 1 else statuses[0]

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    sup._task_status = task_status  # type: ignore[method-assign]
    sup._record_create = noop  # type: ignore[method-assign]
    sup._update_record = noop  # type: ignore[method-assign]
    sup._update_record_by_instance = noop  # type: ignore[method-assign]
    sup._collect_logs = noop  # type: ignore[method-assign]

    async def not_destroyed(_instance_id: int) -> bool:
        return False

    sup._instance_row_destroyed = not_destroyed  # type: ignore[method-assign]
    return sup


@pytest.fixture(autouse=True)
def _fast_settings(monkeypatch):
    monkeypatch.setattr(module.settings, "VAST_SUPERVISOR_INTERVAL", 0)
    monkeypatch.setattr(module.settings, "VAST_RETRY_BACKOFF", 0)
    monkeypatch.setattr(module.settings, "VAST_BOOT_TIMEOUT", 0)
    monkeypatch.setattr(module.settings, "VAST_WORKER_START_TIMEOUT", 0)
    monkeypatch.setattr(module.settings, "VAST_ONESHOT_TIMEOUT", 30)
    monkeypatch.setattr(module.settings, "VAST_MAX_ATTEMPTS", 5)



def test_watch_berhenti_saat_task_selesai():
    sup = _supervisor(_FakeClient([]), ["processing", "completed"])
    outcome, reason = asyncio.run(sup._watch(1))
    assert outcome == "done"
    assert reason == "completed"


def test_watch_menganggap_exited_sebagai_gagal():
    client = _FakeClient(
        [{"actual_status": "exited", "status_msg": "Error: no space left"}]
    )
    sup = _supervisor(client, ["queued"])
    outcome, reason = asyncio.run(sup._watch(1))
    assert outcome == "failed"
    assert "exited" in reason


def test_watch_menganggap_status_msg_error_sebagai_gagal():
    client = _FakeClient(
        [{"actual_status": "running", "status_msg": "Error: pull access denied"}]
    )
    sup = _supervisor(client, ["queued"])
    outcome, reason = asyncio.run(sup._watch(1))
    assert outcome == "failed"
    assert "pull access" in reason


def test_watch_boot_timeout_karena_tidak_pernah_running():
    client = _FakeClient([], default={"actual_status": "loading", "status_msg": ""})
    sup = _supervisor(client, ["queued"])
    outcome, reason = asyncio.run(sup._watch(1))
    assert outcome == "failed"
    assert "boot timeout" in reason


def test_watch_onstart_tidak_pernah_jalan():
    client = _FakeClient([{"actual_status": "running", "status_msg": "success"}] * 3)
    sup = _supervisor(client, ["queued"])
    outcome, reason = asyncio.run(sup._watch(1))
    assert outcome == "failed"
    assert "onstart" in reason


def test_run_mengganti_instance_lalu_berhasil():
    client = _FakeClient([])
    sup = _supervisor(
        client,
        ["queued"],
        offers=[
            {"id": 10, "machine_id": 1, "gpu_name": "RTX 4090", "dph_total": 0.2},
            {"id": 11, "machine_id": 2, "gpu_name": "RTX 4090", "dph_total": 0.25},
        ],
        create_ids=[100, 200],
    )
    outcomes = [("failed", "boom"), ("done", "completed")]

    async def fake_watch(_instance_id: int):
        return outcomes.pop(0)

    destroyed: List[int] = []

    async def fake_destroy(instance_id: int, record_id: Any, reason: str) -> None:
        destroyed.append(instance_id)

    sup._watch = fake_watch  # type: ignore[method-assign]
    sup._destroy = fake_destroy  # type: ignore[method-assign]

    result = asyncio.run(sup.run())
    assert result["ok"] is True
    assert result["attempts"] == 2
    assert destroyed == [100, 200]
    assert sup.exclude_machines == {1}


def test_watch_toleran_404_sesaat():
    """Satu-dua kali None bukan alasan membuang instance (Vast sering telat)."""
    client = _FakeClient([None, None, {"actual_status": "running"}, {"actual_status": "running"}])
    sup = _supervisor(client, ["processing", "processing", "processing", "completed"])
    outcome, reason = asyncio.run(sup._watch(1))
    assert outcome == "done", reason


def test_watch_404_lima_kali_baru_gagal():
    client = _FakeClient([], default=None, existing_ids=[])
    sup = _supervisor(client, ["queued"])
    outcome, reason = asyncio.run(sup._watch(1))
    assert outcome == "failed"
    assert "404" in reason


def test_watch_galat_jaringan_bukan_instance_hilang():
    """Timeout/koneksi putus tidak boleh dihitung sebagai instance hilang."""
    client = _FakeClient(
        [
            TimeoutError("read timeout"),
            OSError("Connection reset by peer"),
            TimeoutError("read timeout"),
            {"actual_status": "running"},
            {"actual_status": "running"},
        ],
        default={"actual_status": "running"},
    )
    sup = _supervisor(client, ["processing", "processing", "processing", "completed"])
    outcome, reason = asyncio.run(sup._watch(1))
    assert outcome == "done", reason


def test_watch_404_tidak_membunuh_task_yang_sedang_processing():
    """404 berulang + task masih processing => instance dipertahankan."""
    client = _FakeClient([], default=None, existing_ids=[])
    sup = _supervisor(client, ["processing"] * 8 + ["completed"])
    outcome, reason = asyncio.run(sup._watch(1))
    assert outcome == "done", reason


def test_watch_berhenti_saat_instance_dihapus_manual():
    """Admin menghapus instance duplikat => supervisor berhenti, tidak respawn."""
    client = _FakeClient([], default=None, existing_ids=[])
    sup = _supervisor(client, ["processing"])

    async def destroyed(_instance_id: int) -> bool:
        return True

    sup._instance_row_destroyed = destroyed  # type: ignore[method-assign]

    outcome, reason = asyncio.run(sup._watch(1))
    assert outcome == "done"
    assert "dihapus manual" in reason
    assert client.destroyed == []


def test_make_create_instance_meneruskan_env_dan_id(monkeypatch):
    from app.services import vast_worker

    captured: Dict[str, Any] = {}

    class _Client:
        def create_instance(self, offer_id: int, **kwargs: Any) -> Dict[str, Any]:
            captured["offer_id"] = offer_id
            captured["kwargs"] = kwargs
            return {"success": True, "new_contract": 4242}

    monkeypatch.setattr(vast_worker.settings, "VAST_WORKER_IMAGE", "user/img:worker")
    monkeypatch.setattr(vast_worker.settings, "VAST_TEMPLATE_HASH", None)
    monkeypatch.setattr(vast_worker.settings, "CLIPZI_CALLBACK_URL", "https://x/api/internal/worker/events")
    monkeypatch.setattr(vast_worker.settings, "CLIPZI_WORKER_TOKEN", "tok")

    create = vast_worker._make_create_instance("00000000-0000-0000-0000-000000000002", _Client())
    instance_id = asyncio.run(create({"id": 99}))

    assert instance_id == 4242
    assert captured["offer_id"] == 99
    assert captured["kwargs"]["image"] == "user/img:worker"
    assert captured["kwargs"]["env"]["CLIPZI_CALLBACK_URL"].endswith("/worker/events")
    assert captured["kwargs"]["label"].startswith("clipzi-")
    assert captured["kwargs"]["onstart_cmd"] == "/app/deployments/pipeline_onstart.sh"


def test_run_gagal_semua_percobaan_menandai_error():
    client = _FakeClient([])
    sup = _supervisor(client, ["queued"], create_ids=[7])
    failures: List[str] = []

    async def fake_watch(_instance_id: int):
        return "failed", "boot rusak"

    async def fake_destroy(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def fake_fail(message: str) -> None:
        failures.append(message)

    sup._watch = fake_watch  # type: ignore[method-assign]
    sup._destroy = fake_destroy  # type: ignore[method-assign]
    sup._fail_task = fake_fail  # type: ignore[method-assign]

    result = asyncio.run(sup.run())
    assert result["ok"] is False
    assert "boot rusak" in result["error"]
    assert len(failures) == 1
    assert "Worker GPU gagal" in failures[0]
