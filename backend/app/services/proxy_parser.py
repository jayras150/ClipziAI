"""
Engine normalisasi daftar proxy.

Masalah: daftar proxy ditempel/diupload dalam banyak format. Kalau string mentah
dikirim ke yt-dlp, hasilnya error membingungkan. Modul ini mengubah semua format
umum menjadi satu bentuk kanonik yang pasti diterima yt-dlp:

    scheme://[user:pass@]host:port

Masukan yang didukung (satu per baris, boleh campur):
    host:port
    host:port:user:pass
    user:pass@host:port
    user:pass:host:port
    scheme://host:port
    scheme://user:pass@host:port
    label|host:port            (label opsional)
    # komentar / baris kosong / pemisah koma, titik-koma, tab

Skema: http, https, socks4, socks5 (+ alias socks). Tanpa skema dipilih otomatis:
port 1080/1081/9050/9150 -> socks5, selain itu http.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Iterable

ALLOWED_SCHEMES = {"http", "https", "socks4", "socks5"}
SCHEME_ALIASES = {"socks": "socks5", "socks5h": "socks5", "socks4a": "socks4"}
SOCKS_PORTS = {1080, 1081, 9050, 9150}
HOST_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
CRED_RE = re.compile(r"^[^\s:@/]+$")
MAX_PROXIES = 2000


@dataclass
class ParsedProxy:
    url: str
    host: str
    port: int
    scheme: str
    username: str | None = None
    password: str | None = None
    label: str | None = None

    def as_item(self) -> dict:
        return {
            "url": self.url,
            "host": self.host,
            "port": self.port,
            "scheme": self.scheme,
            "label": self.label,
        }


def split_lines(raw: str) -> list[str]:
    lines: list[str] = []
    for chunk in (raw or "").replace("\r", "\n").split("\n"):
        for part in re.split(r"[;,\t]", chunk):
            text = part.strip()
            if text and not text.startswith("#") and not text.startswith("//"):
                lines.append(text)
    return lines


def valid_host(host: str) -> bool:
    if not host or len(host) > 253:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    if host == "localhost":
        return True
    return bool(HOST_RE.match(host)) and "." in host


def _build(scheme, host, port_raw, username, password, label) -> ParsedProxy:
    port = int(port_raw)
    if not 1 <= port <= 65535:
        raise ValueError("port tidak valid")
    if not valid_host(host):
        raise ValueError("host tidak valid")
    if scheme:
        cleaned = scheme.lower().strip()
        scheme = SCHEME_ALIASES.get(cleaned, cleaned)
        if scheme not in ALLOWED_SCHEMES:
            raise ValueError("skema tidak didukung")
    else:
        scheme = "socks5" if port in SOCKS_PORTS else "http"
    if username and not CRED_RE.match(username):
        raise ValueError("username tidak valid")
    if password and (":" in password or any(ch.isspace() for ch in password)):
        raise ValueError("password tidak valid")
    credentials = ""
    if username:
        credentials = username + (":" + password if password else "") + "@"
    return ParsedProxy(
        url=scheme + "://" + credentials + host + ":" + str(port),
        host=host,
        port=port,
        scheme=scheme,
        username=username,
        password=password,
        label=label,
    )


def parse_line(line: str) -> ParsedProxy:
    text = (line or "").strip()
    if not text:
        raise ValueError("baris kosong")
    label = None
    if "|" in text:
        maybe_label, _, rest = text.partition("|")
        if rest.strip():
            label = maybe_label.strip()[:40] or None
            text = rest.strip()
    scheme = None
    if "://" in text:
        scheme, _, text = text.partition("://")
        text = text.strip()
        if not text:
            raise ValueError("alamat kosong setelah skema")
    username = None
    password = None
    if "@" in text:
        creds, _, text = text.rpartition("@")
        if ":" in creds:
            username, _, password = creds.partition(":")
        else:
            username = creds or None
    parts = [p for p in text.split(":") if p != ""]
    if len(parts) == 2:
        host, port_raw = parts
    elif len(parts) == 3:
        if parts[1].isdigit():
            host, port_raw, extra = parts
            username = username or (extra or None)
        else:
            username, password, hostpart = parts
            if ":" not in hostpart:
                raise ValueError("port tidak ditemukan")
            host, port_raw = hostpart.split(":", 1)
    elif len(parts) == 4:
        host, port_raw, user_part, pass_part = parts
        if username is None:
            username, password = (user_part or None), (pass_part or None)
    else:
        raise ValueError("format tidak dikenali")
    if not port_raw.isdigit():
        raise ValueError("port bukan angka")
    return _build(scheme, host.strip(), port_raw, username, password, label)


def parse_proxy_text(raw: str) -> dict:
    items: list[dict] = []
    errors: list[dict] = []
    seen: set[str] = set()
    duplicates = 0
    for index, line in enumerate(split_lines(raw), start=1):
        if len(items) >= MAX_PROXIES:
            errors.append({"line": index, "value": "(dipotong)", "reason": "maksimum " + str(MAX_PROXIES) + " proxy"})
            break
        try:
            parsed = parse_line(line)
        except ValueError as exc:
            errors.append({"line": index, "value": line[:80], "reason": str(exc)})
            continue
        if parsed.url in seen:
            duplicates += 1
            continue
        seen.add(parsed.url)
        items.append(parsed.as_item())
    return {
        "items": items,
        "errors": errors,
        "total": len(items) + len(errors) + duplicates,
        "valid": len(items),
        "duplicate": duplicates,
    }


def normalize_many(values: Iterable[str]) -> list[str]:
    urls: list[str] = []
    for value in values:
        urls.extend(item["url"] for item in parse_proxy_text(value)["items"])
    return urls


def mask_url(url: str) -> str:
    if "@" not in (url or ""):
        return url
    scheme, _, rest = url.partition("://")
    _, _, hostpart = rest.rpartition("@")
    return scheme + "://***@" + hostpart
