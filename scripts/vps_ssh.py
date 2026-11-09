"""Deploy Clipzi ke VPS via SSH (non-interaktif, password dari env).

Aksi:
    python vps_ssh.py setup     # paket dasar + swap 2G + folder
    python vps_ssh.py clone     # git clone/pull repo ke /opt/clipzi/app
    python vps_ssh.py config    # tulis backend/.env + docker-compose.yml
    python vps_ssh.py build     # build image frontend di VPS
    python vps_ssh.py up        # docker compose up -d
    python vps_ssh.py status    # ps + health check (backend & via caddy)
    python vps_ssh.py logs      # log backend/frontend/caddy
    python vps_ssh.py shell "<perintah>"

Env: VPS_HOST, VPS_USER, VPS_PASS, VPS_DIR (default /opt/clipzi),
VPS_PUBLIC_URL (default http://<ip>), VPS_REPO, VPS_TAG, VPS_DOCKERHUB.
Password tidak pernah dicetak.
"""
from __future__ import annotations

import os
import sys
import time

import paramiko

from vps_compose import compose_text

HOST = os.environ["VPS_HOST"].strip()
USER = os.environ["VPS_USER"].strip()
PASSWORD = os.environ["VPS_PASS"]
BASE = os.environ.get("VPS_DIR", "/opt/clipzi")
APP = f"{BASE}/app"
PUBLIC_URL = os.environ.get("VPS_PUBLIC_URL", f"http://{HOST}")
REPO = os.environ.get("VPS_REPO", "https://github.com/jayras150/ClipziAI.git")
TAG = os.environ.get("VPS_TAG", "1.5.0")
DOCKERHUB = os.environ.get("VPS_DOCKERHUB", "sujinwo555")


def client() -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30, banner_timeout=30, auth_timeout=30)
    return ssh


def run(ssh: paramiko.SSHClient, cmd: str, timeout: int = 1800, show: bool = True) -> tuple[int, str]:
    chan = ssh.get_transport().open_session()
    chan.settimeout(timeout)
    chan.exec_command(cmd)
    out = b""
    while True:
        if chan.recv_ready():
            out += chan.recv(65536)
        elif chan.exit_status_ready():
            while chan.recv_ready():
                out += chan.recv(65536)
            break
        else:
            time.sleep(0.2)
    code = chan.recv_exit_status()
    text = out.decode("utf-8", "replace")
    if show:
        print(f"\n$ {cmd}")
        print(text.strip()[-4000:] or "(tanpa keluaran)")
        print(f"[exit {code}]")
    return code, text


def write_remote(ssh: paramiko.SSHClient, path: str, content: str, mode: str | None = None) -> None:
    sftp = ssh.open_sftp()
    try:
        with sftp.file(path, "w") as fh:
            fh.write(content)
        if mode:
            sftp.chmod(path, int(mode, 8))
        print(f"tulis: {path} ({len(content)} byte)")
    finally:
        sftp.close()


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    print(f"host={HOST} user={USER} app={APP} url={PUBLIC_URL} tag={TAG}")
    ssh = client()
    try:
        if action == "setup":
            run(ssh, "export DEBIAN_FRONTEND=noninteractive; apt-get update -y >/dev/null && apt-get install -y git curl ca-certificates >/dev/null && echo 'paket OK'", timeout=900)
            run(ssh, "swapon --show | grep -q swapfile || (fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab); free -m | head -2")
            run(ssh, f"mkdir -p {BASE}; df -h / | tail -1")
            run(ssh, "docker --version; docker compose version")
        elif action == "clone":
            run(ssh, f"if [ -d {APP}/.git ]; then cd {APP} && git fetch --all -q && git reset --hard origin/main && git log --oneline -1; else git clone {REPO} {APP} && cd {APP} && git log --oneline -1; fi", timeout=900)
            run(ssh, f"ls -1 {APP} | head -12")
        elif action == "config":
            local_env = open("backend/.env", encoding="utf-8").read()
            write_remote(ssh, f"{APP}/backend/.env", local_env, mode="600")
            write_remote(ssh, f"{APP}/docker-compose.vps.yml", compose_text())
            run(ssh, f"cd {APP} && docker compose -f docker-compose.vps.yml config -q && echo 'compose valid' && ls -l backend/.env docker-compose.yml")
        elif action == "build":
            run(ssh, f"cd {APP} && docker compose -f docker-compose.vps.yml build frontend", timeout=3600)
        elif action == "up":
            run(ssh, f"cd {APP} && docker compose -f docker-compose.vps.yml pull backend && docker compose -f docker-compose.vps.yml up -d", timeout=1800)
            run(ssh, f"cd {APP} && docker compose -f docker-compose.vps.yml ps")
        elif action == "status":
            run(ssh, f"cd {APP} && docker compose -f docker-compose.vps.yml ps")
            run(ssh, "curl -fsS http://127.0.0.1:8000/api/health || echo 'backend health GAGAL'")
            run(ssh, f"curl -s -o /dev/null -w 'api via caddy: %{{http_code}}\\n' {PUBLIC_URL}/api/health; curl -s -o /dev/null -w 'web via caddy: %{{http_code}}\\n' {PUBLIC_URL}/")
            run(ssh, "free -m | head -2; df -h / | tail -1")
        elif action == "logs":
            run(ssh, "docker logs --tail 40 clipzi-api 2>&1 | tail -40")
            run(ssh, "docker logs --tail 20 clipzi-web 2>&1 | tail -20")
            run(ssh, "docker logs --tail 20 clipzi-caddy 2>&1 | tail -20")
        elif action == "shell":
            run(ssh, sys.argv[2], timeout=1800)
        else:
            print(f"aksi tidak dikenal: {action}")
            return 2
    finally:
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

