"""Operasional Vast.ai untuk admin: instance live, log, billing, env, test."""
from __future__ import annotations

import asyncio
import logging
import shlex
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.services.vast_config import normalize_allowlist
from app.services.vast_worker import (
    WORKER_ENV_OPTIONAL,
    WORKER_ENV_REQUIRED,
    _get_vast_client,
    build_worker_env,
)

logger = logging.getLogger(__name__)

RESERVED_ENV = {"PORT", "HOST"}

# Path script onstart di dalam image worker (lihat deployments/pipeline_onstart.sh).
# Template memakai path exec-safe: Vast menjalankan onstart tanpa shell.
TEMPLATE_ONSTART = "/app/deployments/pipeline_onstart.sh"
# Docker options dasar template (port service pipeline; aman & sama seperti CLI lama).
TEMPLATE_DOCKER_OPTIONS = "-p 8000:8000"
# Env yang diisi PER TASK — jangan dibekukan di template.
TEMPLATE_ENV_SKIP = {"CLIPZI_TASK_ID", "CLIPZI_MODEL_URL", "CLIPZI_MODEL_URL_ERROR"}
TEMPLATE_DESC = "ClipziAI worker (dibuat otomatis dari admin) — jangan diedit manual."
# Vast menolak field `env` template > 4096 char:
#   {"error":"invalid_params","msg":"Param env greater than max length 4096 chars"}
# Karena itu env dipotong berprioritas (env wajib dulu) dan sisanya tetap dikirim
# per task lewat create_instance + Environment Variables akun Vast.
TEMPLATE_ENV_MAX_LEN = 4096


def _client():
    key = (get_settings().VAST_API_KEY or "").strip()
    if not key:
        raise RuntimeError(
            "VAST_API_KEY belum diset. Isi lewat Settings › Vast.ai atau backend/.env."
        )
    return _get_vast_client()


async def list_connections() -> List[Dict[str, str]]:
    """Koneksi Cloud Sync milik akun Vast (hanya id + nama, tanpa token)."""
    client = _client()
    try:
        rows = await asyncio.to_thread(client.show_connections)
    except Exception as exc:
        raise RuntimeError(f"Gagal mengambil koneksi Vast: {exc}") from exc
    items: List[Dict[str, str]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        connection_id = str(row.get("id") or "").strip()
        if not connection_id:
            continue
        items.append(
            {
                "id": connection_id,
                "name": str(row.get("name") or connection_id).strip(),
            }
        )
    items.sort(key=lambda item: item["id"])
    return items


def _iso(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return str(value)
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return text


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def test_connection() -> Dict[str, Any]:
    try:
        client = _client()
        user = await asyncio.to_thread(client.show_user)
        instances = await asyncio.to_thread(client.show_instances)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
    return {
        "ok": True,
        "balance": _number((user or {}).get("balance")),
        "total_spend": _number((user or {}).get("total_spend")),
        "username": (user or {}).get("username"),
        "instances": len(instances or []),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def test_offers(limit: int = 5) -> Dict[str, Any]:
    """Cari offer sesuai filter + allowlist + harga, tanpa membuat instance."""
    settings = get_settings()
    client = _client()
    query = (settings.VAST_GPU_FILTER or "").strip()
    try:
        offers = await asyncio.to_thread(
            client.search_offers, query, "on-demand", "dph_total+", 100
        )
    except Exception as exc:
        raise RuntimeError(f"Gagal mencari offer Vast: {exc}") from exc
    cap = float(settings.VAST_ONESHOT_MAX_PRICE or 0)
    allowlist = normalize_allowlist(settings.VAST_GPU_ALLOWLIST)

    def _key(name: Any) -> str:
        import re

        return re.sub(r"[^a-z0-9]", "", str(name or "").lower())

    allowed = {_key(name) for name in allowlist}
    usable: List[Dict[str, Any]] = []
    for offer in offers or []:
        price = _number(offer.get("dph_total")) or 0.0
        if not offer.get("rentable") or price <= 0:
            continue
        if cap > 0 and price > cap:
            continue
        if allowed and _key(offer.get("gpu_name")) not in allowed:
            continue
        usable.append(offer)
    usable.sort(key=lambda item: _number(item.get("dph_total")) or 0)
    selected = usable[: max(1, min(20, int(limit or 5)))]
    return {
        "filter": query,
        "max_price_per_hour": cap or None,
        "gpu_allowlist": allowlist,
        "total_matched": len(usable),
        "offers": [
            {
                "id": offer.get("id"),
                "gpu_name": offer.get("gpu_name"),
                "num_gpus": offer.get("num_gpus"),
                "gpu_ram": offer.get("gpu_ram"),
                "disk_space": offer.get("disk_space"),
                "inet_down": offer.get("inet_down"),
                "price_per_hour": _number(offer.get("dph_total")),
                "machine_id": offer.get("machine_id"),
            }
            for offer in selected
        ],
    }


def _is_secret(name: str) -> bool:
    upper = name.upper()
    return any(
        marker in upper
        for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD", "DATABASE_URL", "ENCRYPTION")
    )


def _mask(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return "****" + text[-4:] if len(text) > 4 else "****"


async def _local_costs(db) -> Dict[str, Any]:
    from sqlalchemy import select

    from app.models.worker_instance import WorkerInstance

    rows = (
        await db.execute(
            select(WorkerInstance).order_by(WorkerInstance.created_at.desc()).limit(500)
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    total = 0.0
    by_day: Dict[str, float] = {}
    for row in rows:
        start = row.ready_at or row.created_at
        if not start:
            continue
        end = row.destroyed_at or now
        seconds = max(0.0, (end - start).total_seconds())
        cost = (_number(row.price_per_hour) or 0.0) * seconds / 3600
        total += cost
        day = start.date().isoformat()
        by_day[day] = by_day.get(day, 0.0) + cost
    return {
        "total_estimated": round(total, 4),
        "by_day": [
            {"date": day, "cost": round(cost, 4)}
            for day, cost in sorted(by_day.items(), reverse=True)[:30]
        ],
        "instances_sampled": len(rows),
    }


def _normalize_invoices(items: Optional[list]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "timestamp": _iso(item.get("timestamp")),
                "amount": _number(item.get("amount")),
                "type": str(item.get("type") or "")[:20],
                "description": str(item.get("description") or "")[:300],
                "instance_id": item.get("instance_id"),
                "quantity": _number(item.get("quantity")),
                "rate": _number(item.get("rate")),
            }
        )
    result.sort(key=lambda row: row.get("timestamp") or "", reverse=True)
    return result


async def billing_summary(
    db,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    invoice_type: Optional[str] = None,
) -> Dict[str, Any]:
    client = _client()
    try:
        user = await asyncio.to_thread(client.show_user)
        raw = await asyncio.to_thread(
            client.show_invoices,
            start_date=start_date or None,
            end_date=end_date or None,
        )
    except Exception as exc:
        raise RuntimeError(f"Gagal mengambil billing Vast: {exc}") from exc
    invoices = _normalize_invoices(
        (raw or {}).get("invoices") if isinstance(raw, dict) else None
    )
    wanted = (invoice_type or "").strip().lower()
    if wanted:
        invoices = [row for row in invoices if row.get("type") == wanted]
    charges = sum(abs(row["amount"] or 0) for row in invoices if row.get("type") == "charge")
    credits = sum(abs(row["amount"] or 0) for row in invoices if row.get("type") == "credit")
    local = await _local_costs(db)
    return {
        "ok": True,
        "account": {
            "username": (user or {}).get("username"),
            "balance": _number((user or {}).get("balance")),
            "total_spend": _number((user or {}).get("total_spend")),
            "credit": _number((user or {}).get("credit")),
        },
        "summary": {
            "invoices": len(invoices),
            "charges": round(charges, 4),
            "credits": round(credits, 4),
            "net": round(charges - credits, 4),
        },
        "invoices": invoices[:200],
        "local": local,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def worker_env_spec() -> List[Dict[str, Any]]:
    """Daftar env worker (satu sumber dengan dispatch instance)."""
    env = build_worker_env()
    items: List[Dict[str, Any]] = [
        {
            "name": "CLIPZI_ROLE",
            "required": True,
            "runtime": True,
            "set": True,
            "secret": False,
            "preview": "worker (otomatis)",
        },
        {
            "name": "CLIPZI_TASK_ID",
            "required": True,
            "runtime": True,
            "set": True,
            "secret": False,
            "preview": "diisi otomatis per task",
        },
    ]
    for name in WORKER_ENV_REQUIRED + WORKER_ENV_OPTIONAL:
        # Cookies yang terlalu besar dikirim sebagai gzip+base64 (`YTDLP_COOKIES_GZIP_B64`)
        # supaya total env di bawah ~4 KB. Dari sudut admin, `YTDLP_COOKIES_BASE64`
        # tetap dianggap "set" walau isinya dikompresi; preview menunjukkan ukuran.
        value = env.get(name, "")
        is_cookie_packed = name == "YTDLP_COOKIES_BASE64" and bool(
            env.get("YTDLP_COOKIES_GZIP_B64")
        )
        effective_value = value or (
            env.get("YTDLP_COOKIES_GZIP_B64") if is_cookie_packed else ""
        )
        secret = _is_secret(name)
        # Cookies tidak lagi dikirim lewat env (CLIPZI_COOKIES_VIA_ENV=0):
        # worker mengambilnya dari endpoint internal. Tanpa penanda ini panel
        # admin akan menampilkan "kosong" padahal cookies tersedia di database
        # (bug lama yang pernah dilaporkan).
        cookies_via_api = (
            name == "YTDLP_COOKIES_BASE64"
            and not value
            and not is_cookie_packed
            and bool(getattr(get_settings(), "YTDLP_COOKIES_BASE64", None))
        )
        items.append(
            {
                "name": name,
                "required": name in WORKER_ENV_REQUIRED,
                "runtime": False,
                "set": bool(effective_value) or cookies_via_api,
                "secret": secret,
                "preview": (
                    _mask(value) if secret else value[:80]
                )
                if value
                else (
                    f"**** (gzip {len(env.get('YTDLP_COOKIES_GZIP_B64') or '')} char)"
                    if is_cookie_packed
                    else (
                        "via API (/api/internal/cookies/active.txt)"
                        if cookies_via_api
                        else ""
                    )
                ),
            }
        )
    return items


def _cookie_env_items(env: Dict[str, str]) -> list:
    """Item env cookies untuk export: gzip+base64 jika dikompresi, else base64."""
    if env.get("YTDLP_COOKIES_GZIP_B64"):
        return [("YTDLP_COOKIES_GZIP_B64", env["YTDLP_COOKIES_GZIP_B64"])]
    if env.get("YTDLP_COOKIES_BASE64"):
        return [("YTDLP_COOKIES_BASE64", env["YTDLP_COOKIES_BASE64"])]
    return []


def env_text(reveal: bool = False) -> str:
    """Export .env worker; nilai secret disamarkan kecuali reveal=True (admin)."""
    env = build_worker_env()
    lines = ["# ClipziAI worker environment (auto-generated)"]
    for name in WORKER_ENV_REQUIRED + WORKER_ENV_OPTIONAL:
        value = env.get(name, "")
        # Jika cookies dikompresi, skip base64 (diganti gzip di bawah).
        if name == "YTDLP_COOKIES_BASE64" and env.get("YTDLP_COOKIES_GZIP_B64"):
            continue
        if value and not reveal and _is_secret(name):
            value = "****"
        if value:
            lines.append(f"{name}={value}")
    for name, value in _cookie_env_items(env):
        if not reveal and name == "YTDLP_COOKIES_GZIP_B64":
            value = f"**** (gzip {len(value)} char)"
        lines.append(f"{name}={value}")
    return "\n".join(lines) + "\n"


async def sync_env_to_vast(
    keys: Optional[List[str]] = None, dry_run: bool = False
) -> Dict[str, Any]:
    """Buat/perbarui environment variable akun Vast dari env backend."""
    client = _client()
    try:
        existing = await asyncio.to_thread(client.show_env_vars, True)
    except TypeError:
        existing = await asyncio.to_thread(client.show_env_vars)
    except Exception as exc:
        raise RuntimeError(f"Gagal membaca env Vast: {exc}") from exc
    existing = existing if isinstance(existing, dict) else {}
    target = build_worker_env()
    selected = (
        list(target.keys()) if not keys else [name for name in keys if name in target]
    )

    results: List[Dict[str, Any]] = []
    for name in selected:
        if name in RESERVED_ENV:
            results.append({"name": name, "action": "skipped_reserved"})
            continue
        value = target.get(name)
        if not value:
            results.append({"name": name, "action": "skipped_empty"})
            continue
        if name not in existing:
            action = "create"
        elif str(existing.get(name)) != str(value):
            action = "update"
        else:
            action = "same"
        if action in ("create", "update") and not dry_run:
            try:
                call = client.create_env_var if action == "create" else client.update_env_var
                await asyncio.to_thread(call, name, value)
            except Exception as exc:
                results.append({"name": name, "action": "error", "error": str(exc)[:200]})
                continue
        results.append({"name": name, "action": action})

    summary: Dict[str, int] = {}
    for row in results:
        summary[row["action"]] = summary.get(row["action"], 0) + 1
    return {"dry_run": dry_run, "results": results, "summary": summary}


# =============================================================================
# Template worker otomatis (image + env pipeline → hash siap dipakai dispatch)
# =============================================================================


def _template_env_items(env: Dict[str, str]) -> List[tuple]:
    """Pasangan (nama, nilai) env template yang terisi & aman untuk shell."""
    items: List[tuple] = []
    for name in sorted(env):
        if name in TEMPLATE_ENV_SKIP:
            continue
        value = str(env.get(name) or "").strip()
        if not value or "\n" in value or "\r" in value:
            continue
        items.append((name, value))
    return items


def _template_env_priority(name: str) -> tuple:
    """Urutan prioritas env template: role → env wajib → sisanya (pendek dulu)."""
    if name == "CLIPZI_ROLE":
        return (0, 0, name)
    if name in WORKER_ENV_REQUIRED:
        return (1, WORKER_ENV_REQUIRED.index(name), name)
    return (2, 0, name)


def build_template_env(
    env: Dict[str, str], max_len: int = TEMPLATE_ENV_MAX_LEN
) -> tuple:
    """Susun docker-options template dengan batas panjang Vast (4096 char).

    Mengembalikan ``(env_string, included, skipped)``. Env yang tidak muat
    dicatat di ``skipped``; nilainya TIDAK hilang karena tetap dikirim per task
    (`create_instance(env=build_worker_env(task_id))`) dan disinkronkan ke
    Environment Variables akun Vast.
    """
    items = _template_env_items(env)
    items.sort(key=lambda kv: (_template_env_priority(kv[0]), len(kv[1]), kv[0]))
    tokens: List[str] = [TEMPLATE_DOCKER_OPTIONS]
    included: List[str] = []
    skipped: List[str] = []
    used = len(TEMPLATE_DOCKER_OPTIONS)
    for name, value in items:
        token = f"-e {name}={shlex.quote(value)}"
        extra = 1 + len(token)  # spasi pemisah + token
        if used + extra > max_len:
            skipped.append(name)
            continue
        tokens.append(token)
        included.append(name)
        used += extra
    return " ".join(tokens), included, skipped


def template_env_string(env: Dict[str, str], max_len: int = TEMPLATE_ENV_MAX_LEN) -> str:
    """Field "Docker options" template Vast (``-p 8000:8000 -e KEY=VALUE …``).

    Nilai di-quote dengan `shlex.quote` karena Vast menyisipkan string ini ke
    perintah ``docker run``. Nilai secret tidak pernah dikembalikan ke UI.
    """
    return build_template_env(env, max_len)[0]


def vast_error_message(exc: BaseException) -> str:
    """Ubah error SDK/HTTP Vast menjadi pesan yang bisa dibaca admin."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    body = ""
    if response is not None:
        try:
            body = (response.text or "").strip()[:400]
        except Exception:  # pragma: no cover - body tidak selalu tersedia
            body = ""
    if status:
        return f"Vast menolak permintaan (HTTP {status}): {body or exc}"
    return f"Gagal memanggil Vast: {exc}"


def _template_hash_from(created: Any) -> str:
    """Ambil ``hash_id`` dari respons ``POST /template/`` (bentuknya bisa beda)."""
    if isinstance(created, dict):
        for key in ("hash_id", "hash", "template_hash"):
            value = created.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        inner = created.get("template")
        if isinstance(inner, str) and inner.strip():
            return inner.strip()
        if isinstance(inner, dict):
            found = _template_hash_from(inner)
            if found:
                return found
    if isinstance(created, str) and len(created.strip()) in {32, 40}:
        return created.strip()
    return ""


def _template_id_from(created: Any) -> Optional[int]:
    """Ambil id numerik template bila respons menyertakannya."""
    if isinstance(created, dict):
        for key in ("id", "template_id"):
            try:
                return int(created[key])  # type: ignore[arg-type]
            except (KeyError, TypeError, ValueError):
                continue
        inner = created.get("template")
        if isinstance(inner, dict):
            return _template_id_from(inner)
    return None


async def _find_template_hash(name: str) -> str:
    """Cari hash template berdasarkan nama (fallback bila respons tanpa hash)."""
    client = _client()
    rows: Any = []
    for query in ({"name": {"eq": name}}, f"name={name}"):
        try:
            rows = await asyncio.to_thread(client.search_templates, query)
            break
        except Exception as exc:  # pragma: no cover - bentuk query bisa berubah
            logger.debug("search_templates(%s) gagal: %s", query, exc)
    newest_hash = ""
    newest_ts = float("-inf")
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("name") or "").strip() != name:
            continue
        hash_id = str(row.get("hash_id") or "").strip()
        if not hash_id:
            continue
        try:
            created_at = float(row.get("created_at") or 0)
        except (TypeError, ValueError):
            created_at = 0.0
        if created_at >= newest_ts:
            newest_hash = hash_id
            newest_ts = created_at
    return newest_hash


def worker_template_spec() -> Dict[str, Any]:
    """Ringkasan template yang dipakai dispatch (tanpa nilai secret)."""
    settings = get_settings()
    env = build_worker_env()
    env_string, env_keys, env_skipped = build_template_env(env)
    template_hash = (settings.VAST_TEMPLATE_HASH or "").strip()
    image = (settings.VAST_WORKER_IMAGE or "").strip()
    api_key = (settings.VAST_API_KEY or "").strip()
    return {
        "template_hash": template_hash,
        "template_name": (settings.VAST_TEMPLATE_NAME or "clipzi-worker").strip(),
        "worker_image": image,
        "worker_disk": int(settings.VAST_WORKER_DISK or 40),
        "onstart": TEMPLATE_ONSTART,
        "docker_options": TEMPLATE_DOCKER_OPTIONS,
        "env_keys": env_keys,
        "env_count": len(env_keys),
        "env_skipped": env_skipped,
        "env_len": len(env_string),
        "env_limit": TEMPLATE_ENV_MAX_LEN,
        "missing_required": [name for name in WORKER_ENV_REQUIRED if not env.get(name)],
        "api_key_set": bool(api_key),
        "ready": bool(api_key) and bool(template_hash or image),
    }


async def worker_template_status(db=None) -> Dict[str, Any]:
    """Status template untuk panel admin (tanpa panggilan jaringan ke Vast)."""
    spec = worker_template_spec()
    if db is not None:
        try:
            drift = await template_drift(db)
            meta = await template_meta(db)
            spec.update(
                {
                    "fingerprint": drift["fingerprint"],
                    "stored_fingerprint": drift["stored_fingerprint"],
                    "drift": drift["drift"],
                    "env_count_current": drift["env_count"],
                    "last_synced_at": meta.get("synced_at"),
                    "active_provider": meta.get("provider"),
                    "template_image": meta.get("image"),
                    "template_disk": meta.get("disk"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - panel tetap tampil
            logger.warning("Gagal membaca metadata template: %s", exc)
    return spec


async def create_worker_template(
    name: Optional[str] = None,
    image: Optional[str] = None,
    disk_space: Optional[int] = None,
    include_env: bool = True,
    sync_env_vars: bool = True,
    public: bool = False,
) -> Dict[str, Any]:
    """Buat template Vast.ai dari image worker + env pipeline (sekali klik).

    Env dibekukan di field `env` template (terlihat di web Vast) dan dibatasi
    4096 char sesuai limit API. `CLIPZI_TASK_ID` TIDAK dibekukan karena diisi
    per task; dispatcher tetap mengirim env lengkap per instance sehingga nilai
    per-task selalu menang (terbukti: env template & instance digabung).
    """
    settings = get_settings()
    client = _client()

    resolved_image = (image or settings.VAST_WORKER_IMAGE or "").strip()
    if not resolved_image:
        raise RuntimeError(
            "VAST_WORKER_IMAGE belum diisi. Isi 'Worker image / tag' lebih dulu, "
            "mis. sujinwo555/clipzi-backend:worker."
        )
    if any(ch.isspace() for ch in resolved_image):
        raise ValueError(f"Image tidak valid: {resolved_image!r}")

    resolved_name = (name or settings.VAST_TEMPLATE_NAME or "clipzi-worker").strip()
    if not resolved_name:
        raise ValueError("Nama template tidak boleh kosong.")

    try:
        disk = int(disk_space or settings.VAST_WORKER_DISK or 40)
    except (TypeError, ValueError) as exc:
        raise ValueError("Storage template harus berupa angka (GB).") from exc
    if disk < 10 or disk > 500:
        raise ValueError("Storage template harus antara 10 dan 500 GB.")

    env = build_worker_env()
    # URL model bertanda tangan kedaluwarsa: jangan dibekukan di template.
    for key in TEMPLATE_ENV_SKIP:
        env.pop(key, None)
    if include_env:
        env_string, env_keys, env_skipped = build_template_env(env)
    else:
        env_string, env_keys, env_skipped = TEMPLATE_DOCKER_OPTIONS, [], sorted(env)

    warnings: List[str] = []
    missing = [key for key in WORKER_ENV_REQUIRED if not env.get(key)]
    if missing:
        warnings.append(f"Env wajib belum diisi di backend: {', '.join(missing)}.")
    if not include_env:
        warnings.append(
            "Env tidak dibekukan di template (opsi dimatikan). Dispatcher mengirim env lengkap "
            "per task dan `sync_env_vars` menyimpannya di Environment Variables akun Vast."
        )
    elif env_skipped:
        shown = ", ".join(env_skipped[:6]) + ("…" if len(env_skipped) > 6 else "")
        warnings.append(
            f"{len(env_skipped)} env tidak dibekukan di template karena batas Vast "
            f"{TEMPLATE_ENV_MAX_LEN} char ({shown}). Nilainya tetap dikirim per task dan "
            "disinkronkan ke Environment Variables akun Vast."
        )

    env_sync: Dict[str, Any] = {"skipped": True}
    if sync_env_vars:
        try:
            env_sync = await sync_env_to_vast(keys=None, dry_run=False)
            env_sync["skipped"] = False
        except Exception as exc:
            env_sync = {"skipped": False, "error": str(exc)[:300]}
            warnings.append(f"Sinkron env ke akun Vast gagal: {str(exc)[:160]}")

    try:
        created = await asyncio.to_thread(
            client.create_template,
            name=resolved_name,
            image=resolved_image,
            env=env_string,
            onstart_cmd=TEMPLATE_ONSTART,
            disk_space=float(disk),
            desc=TEMPLATE_DESC,
            public=bool(public),
        )
    except Exception as exc:
        # Vast membalas 4xx/5xx lewat requests.HTTPError — jangan biarkan jadi 500.
        raise RuntimeError(vast_error_message(exc)) from exc

    template_hash = _template_hash_from(created)
    if not template_hash:
        template_hash = await _find_template_hash(resolved_name)
    if not template_hash:
        warnings.append(
            "Template dibuat tetapi hash tidak terbaca otomatis. Ambil dari dashboard "
            "Vast (Templates) lalu isi manual di kolom 'Template hash'."
        )

    logger.info(
        "Template Vast dibuat: name=%s image=%s hash=%s env=%s skipped=%s",
        resolved_name,
        resolved_image,
        template_hash or "-",
        len(env_keys),
        len(env_skipped),
    )
    return {
        "ok": bool(template_hash),
        "template_hash": template_hash,
        "template_id": _template_id_from(created),
        "name": resolved_name,
        "image": resolved_image,
        "disk_space": disk,
        "onstart": TEMPLATE_ONSTART,
        "docker_options": TEMPLATE_DOCKER_OPTIONS,
        "env_count": len(env_keys),
        "env_keys": env_keys,
        "env_skipped": env_skipped,
        "env_len": len(env_string),
        "env_limit": TEMPLATE_ENV_MAX_LEN,
        "env_included": bool(include_env),
        "env_sync": env_sync,
        "warnings": warnings,
    }

# --- Template per provider model (Clipzy Gdrive / Dropbox / Backblaze / …) ---
PROVIDER_TEMPLATE_DESC = (
    "ClipziAI worker - template otomatis per provider model. Jangan diedit manual."
)


async def _find_template(name: str) -> Optional[Dict[str, Any]]:
    """Cari template Vast berdasarkan nama persis (case-insensitive)."""
    client = _client()
    wanted = str(name or "").strip().lower()
    if not wanted:
        return None
    rows: List[Dict[str, Any]] = []
    for query in (name, {"name": name}):
        try:
            found = await asyncio.to_thread(client.search_templates, query)
        except Exception as exc:  # noqa: BLE001 - biarkan pemanggil memutuskan
            logger.debug("search_templates(%s) gagal: %s", query, exc)
            continue
        if isinstance(found, list) and found:
            rows = found
            break
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("name") or row.get("template_name") or "").strip().lower()
        if label == wanted:
            return row
    return None


PROVIDER_TEMPLATES_KEY = "vast_provider_templates"


async def remembered_templates(db) -> Dict[str, Dict[str, Any]]:
    """Template provider yang pernah dibuat (search_templates Vast tidak selalu
    mengembalikan template private, jadi hasil create/update disimpan di DB)."""
    from app.services import platform_settings as ps

    raw = await ps.get_setting(db, PROVIDER_TEMPLATES_KEY, {})
    items = raw.get("items") if isinstance(raw, dict) else {}
    return items if isinstance(items, dict) else {}


async def remember_template(
    db,
    provider_id: str,
    name: str,
    template_hash: str,
    template_id: Optional[Any] = None,
) -> None:
    from app.services import platform_settings as ps

    items = await remembered_templates(db)
    items[str(provider_id)] = {
        "name": name,
        "template_hash": template_hash,
        "template_id": template_id,
        "updated_at": __import__("datetime").datetime.utcnow().isoformat(),
    }
    await ps.set_setting(db, PROVIDER_TEMPLATES_KEY, {"items": items})


def _template_hash(row: Optional[Dict[str, Any]]) -> str:
    if not isinstance(row, dict):
        return ""
    for key in ("hash_id", "hash", "template_hash"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


async def upsert_worker_template(
    name: str,
    extra_env: Optional[Dict[str, str]] = None,
    *,
    image: Optional[str] = None,
    disk_space: Optional[int] = None,
    public: bool = False,
    known_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Buat/perbarui template Vast untuk satu provider model.

    - Nama template dikunci per provider ("Clipzy Gdrive", "Clipzy Dropbox", …)
      sehingga menyimpan provider berulang tidak membuat duplikat.
    - Env = env worker standar + env khusus provider (dari manifest YAML).
    - Rahasia tidak dibekukan ke template; dispatcher mengirimnya per task.
    """
    settings = get_settings()
    client = _client()
    resolved_name = str(name or "").strip()
    if not resolved_name:
        raise ValueError("Nama template tidak boleh kosong.")
    resolved_image = (image or settings.VAST_WORKER_IMAGE or "").strip()
    if not resolved_image:
        raise RuntimeError(
            "VAST_WORKER_IMAGE belum diisi. Isi 'Worker image / tag' lebih dulu."
        )
    if any(ch.isspace() for ch in resolved_image):
        raise ValueError(f"Image tidak valid: {resolved_image!r}")
    try:
        disk = int(disk_space or settings.VAST_WORKER_DISK or 40)
    except (TypeError, ValueError) as exc:
        raise ValueError("Storage template harus berupa angka (GB).") from exc
    if disk < 10 or disk > 500:
        raise ValueError("Storage template harus antara 10 dan 500 GB.")

    env = build_worker_env()
    # URL model bertanda tangan kedaluwarsa: jangan dibekukan di template.
    for key in TEMPLATE_ENV_SKIP:
        env.pop(key, None)
    for key, value in (extra_env or {}).items():
        if str(value or "").strip():
            env[str(key)] = str(value)
    env_string, env_keys, env_skipped = build_template_env(env)

    warnings: List[str] = []
    missing = [key for key in WORKER_ENV_REQUIRED if not env.get(key)]
    if missing:
        warnings.append(f"Env wajib belum diisi di backend: {', '.join(missing)}.")
    if env_skipped:
        shown = ", ".join(env_skipped[:6]) + ("…" if len(env_skipped) > 6 else "")
        warnings.append(
            f"{len(env_skipped)} env tidak dibekukan di template karena batas Vast "
            f"{TEMPLATE_ENV_MAX_LEN} char ({shown}). Nilainya tetap dikirim per task."
        )

    existing = await _find_template(resolved_name)
    template_hash = _template_hash(existing) or str(known_hash or "").strip()
    action = "updated" if template_hash else "created"
    template_id = None
    if isinstance(existing, dict):
        for key in ("id", "template_id"):
            if existing.get(key) is not None:
                template_id = existing.get(key)
                break

    if template_hash:
        try:
            updated = await asyncio.to_thread(
                client.update_template,
                hash_id=template_hash,
                name=resolved_name,
                image=resolved_image,
                env=env_string,
                onstart_cmd=TEMPLATE_ONSTART,
                disk_space=float(disk),
                desc=PROVIDER_TEMPLATE_DESC,
                public=bool(public),
            )
            template_hash = _template_hash(updated) or template_hash
            template_id = _template_id_from(updated) or template_id
        except Exception as exc:  # noqa: BLE001 - hash lama bisa sudah dihapus
            reason = vast_error_message(exc)
            logger.warning(
                "Template %s tidak bisa diperbarui (%s); dibuat ulang.",
                resolved_name,
                reason[:200],
            )
            warnings.append(
                "Template lama tidak ditemukan/tidak bisa diperbarui "
                f"({reason[:160]}); template dibuat ulang dengan nama yang sama."
            )
            template_hash = ""
            template_id = None
            action = "recreated"

    if not template_hash:
        try:
            created = await asyncio.to_thread(
                client.create_template,
                name=resolved_name,
                image=resolved_image,
                env=env_string,
                onstart_cmd=TEMPLATE_ONSTART,
                disk_space=float(disk),
                desc=PROVIDER_TEMPLATE_DESC,
                public=bool(public),
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(vast_error_message(exc)) from exc
        template_hash = _template_hash(created) or await _find_template_hash(resolved_name)
        template_id = _template_id_from(created)
        if not template_hash:
            warnings.append(
                "Template dibuat tetapi hash tidak terbaca; ambil manual di dashboard Vast."
            )

    logger.info(
        "Template provider %s: action=%s hash=%s env=%s skipped=%s",
        resolved_name,
        action,
        template_hash or "-",
        len(env_keys),
        len(env_skipped),
    )
    return {
        "ok": bool(template_hash),
        "action": action,
        "name": resolved_name,
        "template_hash": template_hash,
        "template_id": template_id,
        "image": resolved_image,
        "disk_space": disk,
        "env_count": len(env_keys),
        "env_keys": env_keys,
        "env_skipped": env_skipped,
        "env_len": len(env_string),
        "env_limit": TEMPLATE_ENV_MAX_LEN,
        "warnings": warnings,
    }


TEMPLATE_META_KEY = "vast_template_meta"


def env_fingerprint(env: Dict[str, str]) -> str:
    # Sidik jari env worker untuk mendeteksi template yang basi.
    # Nilai volatil diabaikan: cookies (gzip memuat timestamp) dan query string
    # pada URL bertanda tangan (presigned) berubah setiap panggilan.
    import hashlib

    parts = []
    for key, value in sorted((env or {}).items()):
        if str(key).startswith("YTDLP_COOKIES_") or key == "CLIPZI_TASK_ID":
            continue
        text = str(value)
        if text.startswith(("http://", "https://")):
            text = text.split("?", 1)[0]
        parts.append(f"{key}={text}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


async def template_meta(db) -> Dict[str, Any]:
    from app.services import platform_settings as ps

    try:
        raw = await ps.get_setting(db, TEMPLATE_META_KEY, {})
    except Exception as exc:  # noqa: BLE001 - metadata bersifat opsional
        logger.warning("Gagal membaca metadata template: %s", exc)
        return {}
    return raw if isinstance(raw, dict) else {}


async def save_template_meta(db, **values) -> Dict[str, Any]:
    from datetime import datetime, timezone

    from app.services import platform_settings as ps

    current = await template_meta(db)
    current.update({key: value for key, value in values.items() if value is not None})
    current["synced_at"] = datetime.now(timezone.utc).isoformat()
    try:
        await ps.set_setting(db, TEMPLATE_META_KEY, current)
    except Exception as exc:  # noqa: BLE001 - jangan gagalkan sync template
        logger.warning("Gagal menyimpan metadata template: %s", exc)
    return current


async def template_drift(db) -> Dict[str, Any]:
    env = build_worker_env()
    meta = await template_meta(db)
    stored = str(meta.get("env_fingerprint") or "")
    current = env_fingerprint(env)
    return {
        "fingerprint": current,
        "stored_fingerprint": stored,
        "drift": bool(stored) and stored != current,
        "env_count": len(env),
        "last_synced_at": meta.get("synced_at"),
    }


async def sync_active_template(
    db,
    *,
    name: Optional[str] = None,
    image: Optional[str] = None,
    disk_space: Optional[int] = None,
    public: bool = False,
    activate: bool = True,
    adopt_hash: Optional[str] = None,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    # SATU pintu template worker: env = build_worker_env() (sudah termasuk provider aktif).
    from app.services import vast_config

    settings = get_settings()
    meta = await template_meta(db)
    env = build_worker_env()
    fingerprint = env_fingerprint(env)

    if adopt_hash:
        hash_id = str(adopt_hash).strip()
        if not hash_id:
            raise ValueError("Hash template kosong.")
        await save_template_meta(
            db,
            template_hash=hash_id,
            name=name or settings.VAST_TEMPLATE_NAME or "clipzi-worker",
            image=image or settings.VAST_WORKER_IMAGE,
            disk=disk_space or settings.VAST_WORKER_DISK,
            env_fingerprint=fingerprint,
            env_count=len(env),
            provider=provider,
            adopted=True,
        )
        if activate:
            await vast_config.save_vast_config(
                db,
                {
                    "template_hash": hash_id,
                    "worker_image": image or settings.VAST_WORKER_IMAGE,
                    "worker_disk": int(disk_space or settings.VAST_WORKER_DISK or 40),
                },
            )
        return {
            "ok": True,
            "adopted": True,
            "template_hash": hash_id,
            "name": name or settings.VAST_TEMPLATE_NAME,
            "image": image or settings.VAST_WORKER_IMAGE,
            "env_count": len(env),
            "fingerprint": fingerprint,
            "activated": bool(activate),
        }

    base_name = str(name or settings.VAST_TEMPLATE_NAME or "clipzy-worker").strip()
    previous_name = str(meta.get("name") or "").strip()
    previous_hash = str(meta.get("template_hash") or "").strip()
    if previous_name and previous_hash:
        resolved_name = previous_name  # update template yang sama, nama tidak berubah
    else:
        seq = int(meta.get("seq") or 0) + 1
        resolved_name = f"{base_name}-{seq}"
        await save_template_meta(db, seq=seq, name=resolved_name)
    result = await upsert_worker_template(
        resolved_name,
        {},
        image=image,
        disk_space=disk_space,
        public=public,
        known_hash=str(meta.get("template_hash") or "") or None,
    )
    hash_id = str(result.get("template_hash") or "")
    await save_template_meta(
        db,
        template_hash=hash_id or None,
        name=result.get("name"),
        image=result.get("image"),
        disk=result.get("disk_space"),
        env_fingerprint=fingerprint,
        env_count=len(env),
        provider=provider,
        adopted=False,
    )
    if activate and hash_id:
        await vast_config.save_vast_config(
            db,
            {
                "template_hash": hash_id,
                "worker_image": result.get("image"),
                "worker_disk": int(result.get("disk_space") or 40),
            },
        )
    result.update(
        {"activated": bool(activate and hash_id), "fingerprint": fingerprint, "drift": False}
    )
    return result


async def provider_templates(db=None) -> Dict[str, Any]:
    """Daftar template per provider model + mana yang sedang aktif."""
    from app.services import model_sources

    settings = get_settings()
    active_hash = (settings.VAST_TEMPLATE_HASH or "").strip()
    remembered: Dict[str, Dict[str, Any]] = {}
    if db is not None:
        try:
            remembered = await remembered_templates(db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("gagal membaca template provider tersimpan: %s", exc)
    items: List[Dict[str, Any]] = []
    for provider in model_sources.providers():
        saved = remembered.get(provider.id) or {}
        row = None
        if not saved.get("template_hash"):
            row = await _find_template(provider.template_name)
        template_hash = str(saved.get("template_hash") or _template_hash(row))
        items.append(
            {
                "provider": provider.id,
                "provider_label": provider.label,
                "name": str(saved.get("name") or provider.template_name),
                "exists": bool(template_hash),
                "template_hash": template_hash,
                "template_id": saved.get("template_id")
                or ((row or {}).get("id") if isinstance(row, dict) else None),
                "active": bool(template_hash) and template_hash == active_hash,
            }
        )
    return {"items": items, "active_hash": active_hash}

