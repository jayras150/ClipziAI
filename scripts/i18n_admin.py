"""Terjemahkan teks UI admin ke bahasa Inggris (sekali jalan)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend/src/app/admin/page.tsx"

PAIRS = [
    ('"Gagal memuat data admin."', '"Could not load admin data."'),
    ('"Pengaturan watermark disimpan."', '"Watermark settings saved."'),
    ('"Gagal menyimpan watermark."', '"Could not save watermark."'),
    ('Alasan ban untuk ${row.email}:', 'Ban reason for ${row.email}:'),
    ('"Gagal mengubah status user."', '"Could not update user status."'),
    ('"Jumlah kredit tidak valid."', '"Invalid credit amount."'),
    ('"Gagal menyesuaikan kredit."', '"Could not adjust credits."'),
    ('["overview", "Ringkasan"]', '["overview", "Overview"]'),
    ('["users", "Pengguna"]', '["users", "Users"]'),
    ('>Watermark platform<', '>Platform watermark<'),
    ('Diterapkan otomatis ke plan terpilih (default free), termasuk hasil merge/split.', 'Applied automatically to the selected plans (default: free), including merge/split results.'),
    ('>Aktifkan watermark wajib<', '>Enable mandatory watermark<'),
    ('htmlFor="wm-text">Teks<', 'htmlFor="wm-text">Text<'),
    ('htmlFor="wm-position">Posisi<', 'htmlFor="wm-position">Position<'),
    ('htmlFor="wm-scale">Ukuran<', 'htmlFor="wm-scale">Size<'),
    ('htmlFor="wm-color">Warna teks<', 'htmlFor="wm-color">Text color<'),
    ('>Berlaku untuk plan<', '>Applies to plans<'),
    ('Berlaku ±60 detik (cache worker).', 'Takes effect within ~60s (worker cache).'),
    ('>aktif<', '>active<'),
    ('>nonaktif<', '>inactive<'),
    ('title="Sesuaikan kredit"', 'title="Adjust credits"'),
    ('>Nama<', '>Name<'),
    ('>Aksi<', '>Action<'),
    ('>Waktu<', '>Time<'),
    ('>Aktor<', '>Actor<'),
    ('Belum ada data.', 'No data yet.'),
    ('Belum ada data<', 'No data yet<'),
    ('Belum ada aktivitas.', 'No activity yet.'),
    ('>Akses ditolak<', '>Access denied<'),
    ('Email akun ini tidak terdaftar di <code>ADMIN_EMAILS</code> pada server.', 'This account email is not listed in <code>ADMIN_EMAILS</code> on the server.'),
    ('>Total user<', '>Total users<'),
    ('>Kredit terpakai<', '>Credits used<'),
    ('total dihasilkan', 'total generated'),
    ('>kumulatif<', '>cumulative<'),
    ('Task per hari · 14 hari', 'Tasks per day · 14 days'),
    ('>Task terbaru<', '>Latest tasks<'),
    ('Kelola watermark platform, pantau aktivitas, dan atur pengguna.', 'Manage the platform watermark, monitor activity, and manage users.'),
]

text = TARGET.read_text(encoding="utf-8")
missing = []
for old, new in PAIRS:
    if old not in text:
        missing.append(old)
        continue
    text = text.replace(old, new)
TARGET.write_text(text, encoding="utf-8")
print(f"admin: {len(PAIRS) - len(missing)}/{len(PAIRS)} replaced")
for item in missing:
    print("   MISSING:", item[:100])
