"""Regresi: noise Docker/Vast & stack trace Go tidak boleh membanjiri log worker.

Gejala asli di dashboard:
  - `ERROR Error response from daemon: No such container: C.61483142`
    (instance sudah dihapus saat log dibaca — bukan kegagalan task)
  - ratusan baris `goroutine 59 ...`, `runtime.gopark(...)`,
    `/usr/local/go/src/...` memenuhi popup log.
"""
from app.services import worker_log_lines as w


def test_noise_docker_dikenali():
    line = "Error response from daemon: No such container: C.61483142".lower()
    assert any(marker in line for marker in w._DROP_MARKERS)


def test_stack_trace_go_dikenali():
    assert w._STACK_LINE.match("goroutine 59 gp=0xc0004b9180 m=nil [GC worker (idle)]")
    assert w._STACK_LINE.match("runtime.gopark(0x0?, 0x0?, 0x0?, 0x0?, 0x0?)")
    assert w._STACK_LINE.match("/usr/local/go/src/runtime/proc.go:424 +0xce")
    assert w._STACK_LINE.match("\t/usr/local/go/src/runtime/mgc.go:1328 +0x25")
    assert w._STACK_LINE.match("created by runtime.gcBgMarkStartWorkers in goroutine 1")


def test_log_normal_tidak_terbuang():
    for line in (
        "download [download] 20%",
        "boot env YTDLP_PROXY=<set> (22 char)",
        "boot env YTDLP_COOKIES_GZIP_B64=<set> (1980 char)",
        "boot GPU: NVIDIA GeForce RTX 3060, 12288 MiB, 570.181",
        "render ffmpeg selesai dalam 12.3s",
    ):
        assert not w._STACK_LINE.match(line)
        assert not any(marker in line.lower() for marker in w._DROP_MARKERS)
