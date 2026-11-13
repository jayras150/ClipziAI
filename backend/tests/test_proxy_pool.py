"""
Test engine normalisasi proxy + pembentukan file proxy aktif.

Pure unit (tanpa DB/jaringan): memastikan semua format umum dikonversi ke
bentuk kanonik yang diterima yt-dlp, dan file active.txt hanya berisi yang aktif.
"""


def test_format_umum_dinormalkan():
    from app.services.proxy_parser import parse_proxy_text

    raw = """
1.2.3.4:8080
1.2.3.5:8080:user:pass
user:pass@1.2.3.6:3128
socks5://1.2.3.7:1080
socks://u:p@1.2.3.8:1080
http://1.2.3.9:8080
label-ku|1.2.3.10:8888
# komentar diabaikan

1.2.3.11:9000, 1.2.3.12:9001
"""
    result = parse_proxy_text(raw)
    urls = [item["url"] for item in result["items"]]

    assert "http://1.2.3.4:8080" in urls
    assert "http://user:pass@1.2.3.5:8080" in urls
    assert "http://user:pass@1.2.3.6:3128" in urls
    assert "socks5://1.2.3.7:1080" in urls
    assert "socks5://u:p@1.2.3.8:1080" in urls
    assert "http://1.2.3.10:8888" in urls
    assert "http://1.2.3.11:9000" in urls
    assert "http://1.2.3.12:9001" in urls
    assert result["valid"] == 9


def test_port_socks_dipilih_otomatis():
    from app.services.proxy_parser import parse_line

    assert parse_line("1.2.3.4:1080").scheme == "socks5"
    assert parse_line("1.2.3.4:9050").scheme == "socks5"
    assert parse_line("1.2.3.4:8080").scheme == "http"


def test_label_dipertahankan():
    from app.services.proxy_parser import parse_line

    parsed = parse_line("sg-1|1.2.3.4:8080")
    assert parsed.label == "sg-1"
    assert parsed.url == "http://1.2.3.4:8080"


def test_duplikat_dan_error_dihitung():
    from app.services.proxy_parser import parse_proxy_text

    result = parse_proxy_text("1.2.3.4:8080\n1.2.3.4:8080\nhost-tanpa-port\n1.2.3.4:99999")
    assert result["valid"] == 1
    assert result["duplicate"] == 1
    assert len(result["errors"]) == 2


def test_mask_url_menyembunyikan_kredensial():
    from app.services.proxy_parser import mask_url

    masked = mask_url("socks5://user:secret@1.2.3.4:1080")
    assert "secret" not in masked
    assert "1.2.3.4:1080" in masked
    assert mask_url("http://1.2.3.4:8080") == "http://1.2.3.4:8080"


def test_active_txt_hanya_proxy_aktif():
    from app.services.proxy_pool import render_active_txt

    items = [
        {"url": "http://a:1", "status": "active"},
        {"url": "http://b:2", "status": "dead"},
        {"url": "http://c:3", "status": "active"},
    ]
    txt = render_active_txt(items)
    assert txt == "http://a:1\nhttp://c:3\n"


def test_normalize_pool_membuang_proxy_mati():
    from app.services.proxy_pool import normalize_pool

    pool = normalize_pool(
        {
            "enabled": True,
            "items": [
                {"url": "http://a:1", "status": "active", "latency_ms": 100},
                {"url": "http://b:2", "status": "dead"},
            ],
        }
    )
    assert pool["active_txt"] == "http://a:1\n"
    assert len(pool["items"]) == 2
    assert pool["items"][0]["status"] == "active"


def test_start_filter_memakai_pool_tersimpan(monkeypatch):
    """START FILTER tanpa input harus menguji proxy yang sudah tersimpan.

    Regresi: dulu kandidat hanya diambil dari payload request, sehingga
    membuka halaman admin lalu menekan START FILTER selalu menjawab
    "Tidak ada proxy valid untuk diuji" dan tidak ada proxy aktif yang terbentuk.
    """
    import asyncio

    from app.services import proxy_pool

    stored = {
        "items": [
            {"url": "http://1.2.3.4:8080", "status": "active"},
            {"url": "socks5://1.2.3.5:1080", "status": "unchecked"},
        ]
    }
    seen: dict = {}

    async def fake_get_pool(db):  # noqa: ANN001 - signature mengikuti aslinya
        assert db is not None
        return stored

    async def fake_run_filter(candidates, target, timeout, concurrency, check_youtube):
        seen["urls"] = [item["url"] for item in candidates]

    monkeypatch.setattr(proxy_pool, "get_pool", fake_get_pool)
    monkeypatch.setattr(proxy_pool, "_run_filter", fake_run_filter)
    monkeypatch.setattr(proxy_pool, "_task", None)

    async def scenario():
        result = await proxy_pool.start_filter(db=object())  # type: ignore[arg-type]
        task = proxy_pool._task
        if task is not None:
            await task
        return result

    result = asyncio.run(scenario())
    assert result["started"] is True
    assert result["total"] == 2
    assert seen["urls"] == ["http://1.2.3.4:8080", "socks5://1.2.3.5:1080"]


def test_start_filter_tanpa_kandidat_menolak(monkeypatch):
    """Tanpa input dan tanpa DB, job tidak boleh jalan (menghindari tes kosong)."""
    import asyncio

    from app.services import proxy_pool

    monkeypatch.setattr(proxy_pool, "_task", None)

    result = asyncio.run(proxy_pool.start_filter())
    assert result["started"] is False
    assert "Tidak ada proxy" in result["message"]
