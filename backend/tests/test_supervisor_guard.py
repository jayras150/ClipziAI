"""Regression test guard destroy instance (tanpa instance GPU nyata)."""
import asyncio

from app.services.instance_supervisor import InstanceSupervisor


async def _value(result):
    return result


def _supervisor():
    return InstanceSupervisor(
        client=object(),
        task_id="task-1",
        offer={"dph_total": 0.2},
        pick_offer=lambda *a, **k: _value({}),
        create_instance=lambda *a, **k: _value(1),
    )


def test_menolak_instance_milik_task_lain(monkeypatch):
    sup = _supervisor()
    monkeypatch.setattr(sup, "_instance_owners", lambda _id: _value({"task-2"}))
    ok, why = asyncio.run(sup._may_destroy(60315038))
    assert ok is False
    assert "task lain" in why


def test_menolak_instance_bukan_milik_supervisor():
    sup = _supervisor()
    sup.current_instance = 111
    ok, why = asyncio.run(sup._may_destroy(222))
    assert ok is False
    assert "supervisor" in why


def test_mengizinkan_saat_task_terminal(monkeypatch):
    sup = _supervisor()
    monkeypatch.setattr(sup, "_instance_owners", lambda _id: _value({"task-1"}))
    monkeypatch.setattr(sup, "_task_status", lambda: _value("completed"))
    ok, why = asyncio.run(sup._may_destroy(60315038))
    assert ok is True, why


def test_menolak_saat_task_masih_jalan(monkeypatch):
    sup = _supervisor()
    monkeypatch.setattr(sup, "_instance_owners", lambda _id: _value({"task-1"}))
    monkeypatch.setattr(sup, "_task_status", lambda: _value("processing"))
    ok, why = asyncio.run(sup._may_destroy(60315038))
    assert ok is False
    assert "processing" in why


def test_mengizinkan_cleanup_saat_supervisor_berhenti(monkeypatch):
    sup = _supervisor()
    sup.allow_destroy_while_running = True
    monkeypatch.setattr(sup, "_instance_owners", lambda _id: _value({"task-1"}))
    monkeypatch.setattr(sup, "_task_status", lambda: _value("processing"))
    ok, why = asyncio.run(sup._may_destroy(60315038))
    assert ok is True, why


def test_db_error_tidak_memblokir_cleanup(monkeypatch):
    sup = _supervisor()

    def boom(_id):
        raise RuntimeError("db mati")

    async def owners(_id):
        raise RuntimeError("db mati")

    monkeypatch.setattr(sup, "_instance_owners", owners)
    monkeypatch.setattr(sup, "_task_status", lambda: _value("completed"))
    ok, why = asyncio.run(sup._may_destroy(60315038))
    assert ok is True, why
