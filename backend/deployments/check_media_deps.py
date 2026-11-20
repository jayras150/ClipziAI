"""Fail-fast: pastikan PyAV kompatibel dengan faster-whisper saat build image.

av 19 menghapus parameter ``metadata_errors`` dari ``av.open()``, sedangkan
faster-whisper 1.2.x masih memakainya di ``decode_audio()``. Tanpa cek ini,
image bisa ter-build "sukses" tetapi semua transkripsi gagal saat runtime
(``TypeError: open() got an unexpected keyword argument 'metadata_errors'``).
"""
import sys


def pyav_supports_metadata_errors(av_module=None) -> bool:
    """True bila ``av.open`` menerima parameter ``metadata_errors``."""
    try:
        av = av_module or __import__("av")
    except Exception:  # noqa: BLE001 - PyAV wajib ada di stage ini
        return False

    try:
        import inspect

        params = inspect.signature(av.open).parameters
    except Exception:  # noqa: BLE001 - signature Cython bisa gagal di versi lain
        params = {}

    if "metadata_errors" in params:
        return True
    return "metadata_errors" in (getattr(av.open, "__doc__", "") or "")


def main() -> int:
    try:
        import av
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: PyAV tidak bisa di-import: {exc}", file=sys.stderr)
        return 1

    if not pyav_supports_metadata_errors(av):
        print(
            "FATAL: av %s tidak punya parameter 'metadata_errors' — "
            "faster-whisper akan gagal decode audio. Pin av>=17,<19."
            % getattr(av, "__version__", "?"),
            file=sys.stderr,
        )
        return 1

    print(
        "OK: av %s kompatibel dengan faster-whisper (metadata_errors tersedia)"
        % getattr(av, "__version__", "?")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
