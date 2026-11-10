"""
Buat / perbarui akun admin ClipzyAI.

Contoh (di VPS):
  docker exec -it clipzi-api /opt/venv/bin/python -m scripts.create_admin \
      --email admin@clipzy.ai --password 'RahasiaKuat123!' --role super_admin

Password TIDAK disimpan di repo; selalu lewat argumen/terminal.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal, init_db  # noqa: E402
from app.models.admin_user import AdminRole, AdminUser  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="Buat/perbarui admin ClipzyAI")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="Owner")
    parser.add_argument(
        "--role", default="super_admin", choices=[r.value for r in AdminRole]
    )
    args = parser.parse_args()

    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AdminUser).where(AdminUser.email == args.email.lower())
        )
        admin = result.scalar_one_or_none()
        if admin:
            admin.password_hash = hash_password(args.password)
            admin.role = AdminRole(args.role)
            admin.is_active = True
            admin.failed_login_attempts = 0
            admin.lock_until = None
            action = "diperbarui"
        else:
            admin = AdminUser(
                email=args.email.lower(),
                password_hash=hash_password(args.password),
                name=args.name,
                role=AdminRole(args.role),
                is_active=True,
                can_adjust_credits=True,
                can_ban_users=True,
                can_manage_plans=True,
                can_view_audit=True,
            )
            db.add(admin)
            action = "dibuat"
        await db.commit()
        print(f"OK admin {action}: {admin.email} ({admin.role.value}) id={admin.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
