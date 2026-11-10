"""Terjemahkan teks UI dashboard ke bahasa Inggris (sekali jalan)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend/src/app/dashboard/page.tsx"

PAIRS = [
    ('(estimasi — klip lama tanpa transkrip tersimpan)', '(estimated — older clip without a stored transcript)'),
    ('"Clipboard kosong — salin link video dulu."', '"Clipboard is empty — copy a video link first."'),
    ('"Link ditempel dari clipboard."', '"Link pasted from clipboard."'),
    ('"Clipboard API tidak tersedia"', '"Clipboard API is not available"'),
    ('"Opsi editing dikembalikan ke default."', '"Editing options reset to default."'),
    ('Skor viral klip #${clip.clip_index + 1} diperbarui: ', 'Viral score for clip #${clip.clip_index + 1} updated: '),
    ('"Compose dibuat tetapi gagal dikirim ke worker."', '"Merge created but it could not be sent to the worker."'),
    ('Gabungan ${selectedClips.length} klip sedang diproses.', 'Merging ${selectedClips.length} clip(s) — processing.'),
    ('Titik potong harus antara 0 dan ${clip.duration.toFixed(1)} detik.', 'Split point must be between 0 and ${clip.duration.toFixed(1)} seconds.'),
    ('"Split dibuat tetapi gagal dikirim ke worker."', '"Split created but it could not be sent to the worker."'),
    ('Klip #${clip.clip_index} dipotong di ${value.toFixed(1)} detik.', 'Clip #${clip.clip_index} split at ${value.toFixed(1)} seconds.'),
    ('s per klip · estimasi render ±', 's per clip · estimated render ±'),
    ('} menit`', '} min`'),
    ('"3 klip · estimasi render ±3–5 menit · 1 credit/klip"', '"3 clips · estimated render ±3–5 min · 1 credit/clip"'),
    ('<option value="9:16">9:16 vertikal</option>', '<option value="9:16">9:16 vertical</option>'),
    ('<option value="1:1">1:1 persegi</option>', '<option value="1:1">1:1 square</option>'),
    ('<option value="16:9">16:9 landskap</option>', '<option value="16:9">16:9 landscape</option>'),
    ('placeholder="teks overlay"', 'placeholder="overlay text"'),
    ('htmlFor="caption-style">Style subtitle</label>', 'htmlFor="caption-style">Subtitle style</label>'),
    ('htmlFor="speed">Kecepatan</label>', 'htmlFor="speed">Speed</label>'),
    ('<summary>Opsi editing lanjutan</summary>', '<summary>Advanced editing options</summary>'),
    ('title="Kembalikan semua opsi editing ke default"', 'title="Reset all editing options to default"'),
    ('<RotateCcw size={14} /> Reset opsi', '<RotateCcw size={14} /> Reset options'),
    ('title="Semua klip plan free otomatis diberi watermark Clipzy. Upgrade untuk menghapus."', 'title="All free-plan clips include the Clipzy watermark. Upgrade to remove it."'),
    ('Centang klip untuk digabung ({selectedClips.length} dipilih)', 'Select clips to merge ({selectedClips.length} selected)'),
    ('<Layers size={13} /> Gabung {selectedClips.length || ""}', '<Layers size={13} /> Merge {selectedClips.length || ""}'),
    ('aria-label={`Buka klip ${clip.clip_index + 1}`}', 'aria-label={`Open clip ${clip.clip_index + 1}`}'),
    ('title="Pilih untuk digabung"', 'title="Select for merge"'),
    ('<span>Gabung</span>', '<span>Merge</span>'),
    ('title="Titik potong (detik)"', 'title="Split point (seconds)"'),
    ('title="Split di titik ini"', 'title="Split at this point"'),
    ('label: "Bawaan"', 'label: "Default"'),
    ('label: "Classic putih"', 'label: "Classic white"'),
    ('label: "Gold tebal"', 'label: "Bold gold"'),
    ('label: "Kotak hitam"', 'label: "Black box"'),
    ('label: "Atas bersih"', 'label: "Clean top"'),
    ('label: "Hook tengah"', 'label: "Center hook"'),
]

text = TARGET.read_text(encoding="utf-8")
missing = []
for old, new in PAIRS:
    if old not in text:
        missing.append(old)
        continue
    text = text.replace(old, new)
TARGET.write_text(text, encoding="utf-8")
print(f"dashboard: {len(PAIRS) - len(missing)}/{len(PAIRS)} replaced")
for item in missing:
    print("   MISSING:", item[:100])
