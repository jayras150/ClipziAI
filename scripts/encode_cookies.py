#!/usr/bin/env python3
"""
Encode file cookies.txt (format Netscape) menjadi base64 untuk env
YTDLP_COOKIES_BASE64.

Cara pakai:
    python scripts/encode_cookies.py cookies.txt

Hasilnya satu baris base64 panjang -> tempel ke backend/.env:

    YTDLP_COOKIES_BASE64=<hasil>

Untuk Docker, cara ini paling praktis karena tidak perlu mount file.

Cara mendapatkan cookies.txt:
  1. Login YouTube di browser (pakai akun yang boleh akses video target).
  2. Pasang ekstensi "Get cookies.txt LOCALLY" (Chrome/Firefox).
  3. Buka youtube.com, klik ekstensi -> Export -> simpan cookies.txt.

PENTING: cookies = kredensial login. Jangan commit cookies.txt,
jangan pakai akun utama, dan rotate (logout) bila file bocor.
"""
import base64
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/encode_cookies.py <cookies.txt>", file=sys.stderr)
        return 1

    source = Path(sys.argv[1])
    if not source.exists():
        print(f"File tidak ditemukan: {source}", file=sys.stderr)
        return 1

    raw = source.read_bytes()
    if b"Netscape HTTP Cookie File" not in raw and b"\t" not in raw:
        print(
            "PERINGATAN: file tidak terlihat seperti format Netscape cookies.txt.\n"
            "Pastikan mengekspor dengan ekstensi 'Get cookies.txt LOCALLY'.",
            file=sys.stderr,
        )

    encoded = base64.b64encode(raw).decode("ascii")

    print()
    print("=== Salin baris di bawah ke backend/.env ===")
    print(f"YTDLP_COOKIES_BASE64={encoded}")
    print()
    print(f"(panjang base64: {len(encoded)} karakter, file: {len(raw)} byte)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
