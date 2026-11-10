"""Batch 2: sisa teks Indonesia di dashboard + admin."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DASHBOARD_PAIRS = [
    ('`Durasi pas: ${pct("duration")}`', '`Duration fit: ${pct("duration")}`'),
    ('title="Kembali ke halaman sebelumnya"', 'title="Go back to the previous page"'),
    ('<ArrowLeft size={14} /> Kembali', '<ArrowLeft size={14} /> Back'),
    ('htmlFor="start-time">Mulai detik<', 'htmlFor="start-time">Start (s)<'),
    ('htmlFor="end-time">Akhir detik<', 'htmlFor="end-time">End (s)<'),
    ('htmlFor="watermark-position">Posisi watermark<', 'htmlFor="watermark-position">Watermark position<'),
    ('htmlFor="music-track">Musik<', 'htmlFor="music-track">Music<'),
    ('<option value="">tanpa musik</option>', '<option value="">no music</option>'),
    ('htmlFor="music-volume">Volume musik<', 'htmlFor="music-volume">Music volume<'),
    ('<span>Perbaiki audio</span>', '<span>Clean audio</span>'),
    ('<span>Ducking musik saat bicara</span>', '<span>Duck music while speaking</span>'),
    ('title="Buka video, metadata AI, download, upload YouTube"', 'title="Open video, AI metadata, download, upload to YouTube"'),
]

ADMIN_PAIRS = [
    ('`Tambah/kurangi kredit ${row.email} (contoh: 5 atau -3):`', '`Add/subtract credits for ${row.email} (e.g. 5 or -3):`'),
    ('`Kredit ${row.email}: ${amount > 0 ? "+" : ""}${amount} → saldo ${result.new_balance}`', '`Credits ${row.email}: ${amount > 0 ? "+" : ""}${amount} → balance ${result.new_balance}`'),
    ('<ArrowLeft size={14} /> Kembali', '<ArrowLeft size={14} /> Back'),
]


def apply(relative: str, pairs: list[tuple[str, str]]) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    missing = []
    for old, new in pairs:
        if old not in text:
            missing.append(old)
            continue
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    print(f"{relative}: {len(pairs) - len(missing)}/{len(pairs)}")
    for item in missing:
        print("   MISSING:", item[:100])


apply("frontend/src/app/dashboard/page.tsx", DASHBOARD_PAIRS)
apply("frontend/src/app/admin/page.tsx", ADMIN_PAIRS)
