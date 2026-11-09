"""Bootstrap VPS jadi environment coding (dipanggil sekali, pakai password).

Aksi:
    python vps_dev.py key         # pasang SSH public key lokal -> authorized_keys
    python vps_dev.py tools       # git, build-essential, python3, node, tmux, dll
    python vps_dev.py codeserver  # code-server (VS Code di browser) di :8443
    python vps_dev.py status      # ringkasan versi & service

Env: VPS_HOST, VPS_USER, VPS_PASS, VPS_PUBKEY (path file .pub lokal).
"""
from __future__ import annotations

import os
import sys
import time

import paramiko

HOST = os.environ["VPS_HOST"].strip()
USER = os.environ["VPS_USER"].strip()
PASSWORD = os.environ["VPS_PASS"]
PUBKEY = os.environ.get(
    "VPS_PUBKEY", os.path.expanduser("~/.ssh/id_ed25519.pub")
)
CS_PORT = os.environ.get("VPS_CODE_PORT", "8443")


def client() -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30, banner_timeout=30, auth_timeout=30)
    return ssh


def run(ssh: paramiko.SSHClient, cmd: str, timeout: int = 1800) -> tuple[int, str]:
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
    print(f"\n$ {cmd}")
    print(text.strip()[-4500:] or "(tanpa keluaran)")
    print(f"[exit {code}]")
    return code, text


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    print(f"host={HOST} user={USER} code-server port={CS_PORT}")
    ssh = client()
    try:
        if action == "key":
            key = open(PUBKEY, encoding="utf-8").read().strip()
            sftp = ssh.open_sftp()
            try:
                run(ssh, "mkdir -p /root/.ssh && chmod 700 /root/.ssh && touch /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys")
                remote = "/root/.ssh/authorized_keys"
                existing = ""
                try:
                    with sftp.file(remote, "r") as fh:
                        existing = fh.read().decode("utf-8", "replace")
                except OSError:
                    existing = ""
                if key not in existing:
                    with sftp.file(remote, "a") as fh:
                        fh.write(key + "\n")
                    print("public key ditambahkan")
                else:
                    print("public key sudah ada")
            finally:
                sftp.close()
            run(ssh, "wc -l /root/.ssh/authorized_keys; grep -c 'cline-vps' /root/.ssh/authorized_keys")
        elif action == "tools":
            run(ssh, "export DEBIAN_FRONTEND=noninteractive; apt-get update -y >/dev/null && apt-get install -y git curl wget unzip zip tar build-essential python3 python3-pip python3-venv python3-dev tmux htop nano vim jq tree ripgrep rsync ca-certificates gnupg openssh-client >/dev/null && echo 'paket dev OK'", timeout=1200)
            run(ssh, "git --version; python3 --version; pip3 --version; node -v 2>/dev/null || echo 'node: belum ada'; npm -v 2>/dev/null || echo 'npm: belum ada'")
        elif action == "node":
            run(ssh, "curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null 2>&1 && apt-get install -y nodejs >/dev/null && echo 'node 20 OK'", timeout=1200)
            run(ssh, "node -v; npm -v; which npx")
        elif action == "codeserver":
            run(ssh, "curl -fsSL https://code-server.dev/install.sh | sh >/dev/null 2>&1 && echo 'code-server terpasang'", timeout=1200)
            run(ssh, f"sed -i 's/^bind-addr:.*/bind-addr: 0.0.0.0:{CS_PORT}/' /root/.config/code-server/config.yaml 2>/dev/null || true; cat /root/.config/code-server/config.yaml 2>/dev/null")
            run(ssh, "systemctl enable --now code-server@root >/dev/null 2>&1; systemctl is-active code-server@root; ss -tlnp | grep 8443 || true")
        elif action == "status":
            run(ssh, "cat /etc/os-release | head -2; nproc; free -m | head -2; df -h / | tail -1")
            run(ssh, "git --version; python3 --version; node -v 2>/dev/null; npm -v 2>/dev/null; docker --version; docker compose version")
            run(ssh, f"systemctl is-active code-server@root 2>/dev/null || echo 'code-server: tidak aktif'; ls -l /root/.ssh/authorized_keys")
        else:
            print(f"aksi tidak dikenal: {action}")
            return 2
    finally:
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
