"""Terjemahkan pesan metadata + transcriber ke bahasa Inggris."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

METADATA = [
    ('"AI membalas kosong."', '"AI returned an empty response."'),
    ('"Balasan AI bukan JSON."', '"AI response is not JSON."'),
    ('f"JSON dari AI tidak valid: {exc.msg}"', 'f"AI returned invalid JSON: {exc.msg}"'),
    ('"JSON dari AI bukan objek."', '"AI JSON is not an object."'),
    ('"AI belum dikonfigurasi di server (isi AI_PROVIDER/AI_API_KEY). "\n                "Metadata tidak dibuat agar tidak asal-asalan."',
     '"AI is not configured on the server (set AI_PROVIDER/AI_API_KEY). "\n                "No metadata was generated to avoid inventing content."'),
    ('"Transkrip klip terlalu pendek untuk dijadikan dasar metadata. "\n                "Proses ulang video dengan transkripsi Whisper aktif."',
     '"The clip transcript is too short to ground the metadata. "\n                "Reprocess the video with Whisper transcription enabled."'),
    ('"AI tidak berhasil membuat metadata dari transkrip (balasan kosong/terputus). "\n            f"Coba lagi. Detail: {str(last_error)[:200]}"',
     '"AI could not produce metadata from the transcript (empty or truncated response). "\n            f"Please try again. Detail: {str(last_error)[:200]}"'),
    ('"AI tidak menghasilkan judul."', '"AI did not produce a title."'),
    ('"AI memakai kalimat template; metadata ditolak."',
     '"AI used template wording, so the metadata was rejected."'),
    ('"AI tidak menghasilkan deskripsi."', '"AI did not produce a description."'),
    ('"Judul dari AI tidak nyambung dengan isi transkrip; metadata ditolak."',
     '"The AI title does not match the transcript, so the metadata was rejected."'),
    ('"Tag dari AI terlalu umum / tidak terkait isi video; metadata ditolak."',
     '"The AI tags are too generic or unrelated to the video, so the metadata was rejected."'),
    ('"Semua tag generik; metadata ditolak."', '"All tags are generic, so the metadata was rejected."'),
]

TRANSCRIBER = [
    ('"TRANSCRIPTION_API_KEY wajib diisi untuk provider transkripsi non-local."',
     '"TRANSCRIPTION_API_KEY is required for a non-local transcription provider."'),
    ('"Transkripsi lokal butuh paket faster-whisper yang tidak dipasang "',
     '"Local transcription needs the faster-whisper package, which is not installed "'),
    ('"secara default. Jalankan: "', '"by default. Run: "'),
    ('"pip install -r requirements-whisper-local.txt â€” atau pakai "',
     '"pip install -r requirements-whisper-local.txt — or use "'),
    ('"TRANSCRIPTION_PROVIDER berbasis API (groq/openai/openrouter)."',
     '"an API-based TRANSCRIPTION_PROVIDER (groq/openai/openrouter)."'),
    ('f"Transkripsi GPU gagal: {str(exc)[:300]}"', 'f"GPU transcription failed: {str(exc)[:300]}"'),
    ('f"Transkripsi melalui provider \'{self.provider}\' gagal di semua format: "',
     'f"Transcription through provider \'{self.provider}\' failed for every format: "'),
    ('f"Provider \'{self.provider}\' menolak karena kredit/kuota: {str(exc)[:200]}"',
     'f"Provider \'{self.provider}\' refused the request (credit/quota): {str(exc)[:200]}"'),
    ('f"Transkripsi gagal: provider \'{self.provider}\' error "\n                    f"({str(exc)[:200]}) dan fallback lokal juga gagal "\n                    f"({str(local_exc)[:200]})."',
     'f"Transcription failed: provider \'{self.provider}\' error "\n                    f"({str(exc)[:200]}) and the local fallback failed too "\n                    f"({str(local_exc)[:200]})."'),
]


def apply(relative: str, pairs) -> None:
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
        print("   MISSING:", item.splitlines()[0][:100])


apply("backend/app/services/metadata_generator.py", METADATA)
apply("backend/app/services/transcriber.py", TRANSCRIBER)
