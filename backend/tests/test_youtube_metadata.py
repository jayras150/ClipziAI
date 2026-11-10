"""Unit test sanitasi metadata YouTube (mencegah 400 invalidTitle/invalidTags)."""
from app.services.youtube_metadata import (
    MAX_TITLE,
    MAX_TAGS_TOTAL,
    build_snippet,
    normalize_category,
    normalize_privacy,
    sanitize_description,
    sanitize_tags,
    sanitize_title,
)


def test_title_membuang_karakter_terlarang_dan_membatasi_panjang():
    dirty = "<script>Halo</script>\x00 dunia" + "x" * 200
    clean = sanitize_title(dirty)
    assert "<" not in clean and ">" not in clean
    assert "\x00" not in clean
    assert len(clean) <= MAX_TITLE
    assert clean.startswith("script Halo")


def test_title_kosong_memakai_fallback():
    assert sanitize_title("   ", fallback="Shorts") == "Shorts"


def test_description_mempertahankan_baris_baru():
    text = "Baris satu <b>tebal</b>\n\n#hashtag #kedua"
    clean = sanitize_description(text)
    assert "<b>" not in clean
    assert "\n\n" in clean
    assert clean.endswith("#hashtag #kedua")


def test_tags_dedup_dan_batas_total():
    tags = ["Sama", "sama", "  spasi  ganda "] + [f"tag-{i}" for i in range(40)]
    clean = sanitize_tags(tags)
    assert len(clean) <= 15
    assert sum(len(tag) for tag in clean) <= MAX_TAGS_TOTAL
    lowered = [tag.lower() for tag in clean]
    assert len(lowered) == len(set(lowered))


def test_tags_membuang_karakter_berbahaya():
    clean = sanitize_tags(["a<b>c", "biasa"])
    assert clean == ["a b c", "biasa"]


def test_privacy_dan_kategori_aman():
    assert normalize_privacy("public") == "public"
    assert normalize_privacy("aneh") == "unlisted"
    assert normalize_category("24") == "24"
    assert normalize_category("999") == "22"
    assert normalize_category(None) == "22"


def test_build_snippet_lengkap():
    snippet = build_snippet(
        title="Judul <keren>",
        description="Deskripsi\n#tag",
        tags=["satu", "dua", "satu"],
        category_id="24",
    )
    assert snippet["title"] == "Judul keren"
    assert snippet["tags"] == ["satu", "dua"]
    assert snippet["categoryId"] == "24"
    assert "\n" in snippet["description"]
