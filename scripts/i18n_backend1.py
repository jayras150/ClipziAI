"""Terjemahkan pesan API (YouTube + klip) yang tampil di UI ke bahasa Inggris."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

YOUTUBE_API = [
    ('"Akun YouTube belum terhubung. Hubungkan dulu dari halaman Profil/Dashboard."',
     '"YouTube is not connected yet. Connect it from the Profile or Dashboard page first."'),
    ('"Klip ini tidak punya file video untuk diunggah."',
     '"This clip has no video file to upload."'),
    ('"Transkrip klip belum siap. Buka popup klip, tekan "',
     '"The clip transcript is not ready. Open the clip popup, click "'),
    ('"\\"Generate ulang AI\\" sampai judul muncul, lalu upload lagi."',
     '"\\"Regenerate with AI\\" until a title appears, then upload again."'),
    ('f"Upload YouTube gagal: {str(exc)[:300]}"', 'f"YouTube upload failed: {str(exc)[:300]}"'),
    ('"State OAuth YouTube tidak valid atau sudah kedaluwarsa."',
     '"The YouTube OAuth state is invalid or has expired."'),
]

YOUTUBE_SERVICE = [
    ('"YouTube belum dikonfigurasi. Administrator harus mengisi "',
     '"YouTube is not configured yet. An administrator must set "'),
    ('"YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, dan "',
     '"YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and "'),
    ('"YOUTUBE_REDIRECT_URI di environment server."',
     '"YOUTUBE_REDIRECT_URI in the server environment."'),
    ('f"Google menolak otorisasi YouTube: {response.text[:300]}"',
     'f"Google rejected the YouTube authorization: {response.text[:300]}"'),
    ('"Google tidak mengembalikan access token YouTube."',
     '"Google did not return a YouTube access token."'),
    ('f"Gagal membaca channel YouTube: {response.text[:300]}"',
     'f"Could not read the YouTube channel: {response.text[:300]}"'),
    ('"Akun Google ini belum memiliki channel YouTube yang dapat digunakan."',
     '"This Google account has no usable YouTube channel."'),
    ('"Token YouTube sudah kedaluwarsa dan tidak ada refresh token. "',
     '"The YouTube token expired and no refresh token is available. "'),
    ('"Hubungkan ulang akun YouTube dari halaman Profil/Dashboard."',
     '"Reconnect your YouTube account from the Profile or Dashboard page."'),
    ('"Gagal memperbarui token YouTube. Hubungkan ulang akun "',
     '"Could not refresh the YouTube token. Reconnect your "'),
    ('f"YouTube. ({response.text[:200]})"', 'f"YouTube account. ({response.text[:200]})"'),
    ('"Sumber video tidak tersedia (file maupun URL kosong)."',
     '"No video source available (empty file and URL)."'),
]

CLIPS_API = [
    ('"ID klip tidak valid."', '"Invalid clip id."'),
    ('"Klip tidak ditemukan."', '"Clip not found."'),
    ('"Klip ini belum punya file video, jadi transkrip tidak bisa dibuat."',
     '"This clip has no video file, so a transcript cannot be created."'),
    ('"Audio klip ini tidak mengandung ucapan yang cukup, jadi metadata "\n                "tidak bisa dibuat dari transkrip (tidak mau dikarang)."',
     '"This clip has too little speech to ground the metadata, so nothing was generated."'),
    ('"Transkripsi gagal."', '"Transcription failed."'),
    ('"Transkrip klip gagal dibuat: provider Whisper menolak (kredit habis) "\n            "dan Whisper lokal gagal dimuat. Coba lagi beberapa saat, atau proses "\n            "ulang video agar transkrip tersimpan."',
     '"Could not create the clip transcript: the Whisper provider refused the request (out of credit) "\n            "and the local Whisper model could not load. Try again shortly, or reprocess the video so a transcript is stored."'),
    ('"Kredit layanan Whisper habis. Metadata tidak dibuat agar tidak "\n            "mengarang isi video; top up kredit atau proses ulang video."',
     '"The Whisper transcription credit is exhausted. No metadata was generated to avoid inventing content; "\n            "top up the credit or reprocess the video."'),
    ('f"Gagal membuat transkrip klip: {str(exc)[:300]}"',
     'f"Could not create the clip transcript: {str(exc)[:300]}"'),
    ('"Transkrip klip ini tidak tersedia sehingga metadata tidak dibuat: "',
     '"This clip has no transcript, so no metadata was created: "'),
    ('"Menyiapkan transkrip klip (SRT/Whisper) lalu metadata dibuat AI. "\n                "Biasanya selesai dalam 1-2 menit."',
     '"Preparing the clip transcript (SRT/Whisper); AI metadata follows. "\n                "This usually takes 1-2 minutes."'),
    ('if "fallback lokal juga gagal" in low or "whisper lokal" in low:',
     'if "local whisper" in low or "fallback lokal juga gagal" in low or "whisper lokal" in low:'),
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


apply("backend/app/api/youtube.py", YOUTUBE_API)
apply("backend/app/services/youtube_service.py", YOUTUBE_SERVICE)
apply("backend/app/api/clips.py", CLIPS_API)
