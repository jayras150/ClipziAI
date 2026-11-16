"""Gagal bila masih ada teks Indonesia yang terlihat user di frontend/src.

Dipakai sebelum build image frontend agar UI client tetap 100% Inggris.
Komentar kode (//, /*, *) diabaikan karena tidak tampil di UI.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "src"
WORDS = (
    "tidak|yang|untuk|dengan|sudah|belum|adalah|akan|kami|anda|atau|juga|bisa|harus|"
    "sedang|gagal|berhasil|silakan|masuk|keluar|simpan|unggah|unduh|hapus|batal|profil|"
    "pengaturan|riwayat|tugas|kredit|langganan|pembayaran|akun|sandi|daftar|selesai|"
    "menunggu|memuat|tutup|pilih|coba|lagi|semua|baru|tanpa|hanya|lebih|paling|jika|"
    "karena|agar|supaya|tetapi|namun|setiap|milik|kepada|dalam|pada|seperti|kembali|"
    "selanjutnya|sebelumnya|yakin|ubah|salin|tempel|berkas|waktu|tanggal|menit|detik|"
    "kamu|kita|tersebut|oleh|perlu|ingin|mengapa|bagaimana|dan|ini|itu|gratis|bulan|"
    "tahun|paket|harga|bayar|tagihan|hemat|diskon|populer|unggulan|tersedia|memproses|"
    "mengunggah|mengunduh|menyalin|menempel|memilih|menghapus|menyimpan|berjalan|mulai"
)
PATTERN = re.compile(rf"\b({WORDS})\b", re.IGNORECASE)


def main() -> int:
    problems: list[str] = []
    for path in sorted(list(ROOT.rglob("*.tsx")) + list(ROOT.rglob("*.ts"))):
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("//", "/*", "*", "{")):
                continue
            if PATTERN.search(stripped):
                problems.append(f"{path.relative_to(ROOT)}:{number}: {stripped[:120]}")
    if problems:
        print("Teks Indonesia ditemukan di UI frontend:")
        for item in problems:
            print(" -", item)
        return 1
    print("OK: tidak ada teks Indonesia di frontend/src")
    return 0


if __name__ == "__main__":
    sys.exit(main())
