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
