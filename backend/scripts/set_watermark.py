"""
Ubah setelan watermark platform tanpa membuka UI admin (cadangan aman).

Contoh:
  docker exec clipzi-api /opt/venv/bin/python -m scripts.set_watermark --show
  docker exec clipzi-api /opt/venv/bin/python -m scripts.set_watermark \
      --enable --text "clipzy.ai" --position bottom-right --opacity 0.85 --scale 0.18
  docker exec clipzi-api /opt/venv/bin/python -m scripts.set_watermark \
      --enable --image-url https://cdn.../logo.png --plans free
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import AsyncSessionLocal, init_db  # noqa: E402
from app.services.platform_settings import (  # noqa: E402
    PLANS,
    POSITIONS,
    get_watermark_config,
    set_watermark_config,
)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Setelan watermark platform")
    parser.add_argument("--show", action="store_true", help="Tampilkan konfigurasi sekarang")
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--disable", action="store_true")
    parser.add_argument("--image-url", default=None)
    parser.add_argument("--text", default=None)
    parser.add_argument("--position", default=None, choices=list(POSITIONS))
    parser.add_argument("--opacity", type=float, default=None)
    parser.add_argument("--scale", type=float, default=None)
    parser.add_argument("--margin", type=int, default=None)
    parser.add_argument("--text-color", default=None)
    parser.add_argument("--plans", default=None, help="Daftar plan dipisah koma, mis. free,standar")
    args = parser.parse_args()

    await init_db()
    async with AsyncSessionLocal() as db:
        config = await get_watermark_config(db)
        if args.show or not any(
            [
                args.enable,
                args.disable,
                args.image_url,
                args.text,
                args.position,
                args.opacity is not None,
                args.scale is not None,
                args.margin is not None,
                args.text_color,
                args.plans,
            ]
        ):
            print(json.dumps(config, indent=2, ensure_ascii=False))
            return 0

        if args.enable:
            config["enabled"] = True
        if args.disable:
            config["enabled"] = False
        if args.image_url is not None:
            config["image_url"] = args.image_url or None
        if args.text is not None:
            config["text"] = args.text or None
        if args.position:
            config["position"] = args.position
        if args.opacity is not None:
            config["opacity"] = args.opacity
        if args.scale is not None:
            config["scale"] = args.scale
        if args.margin is not None:
            config["margin"] = args.margin
        if args.text_color:
            config["text_color"] = args.text_color
        if args.plans:
            chosen = [p.strip().lower() for p in args.plans.split(",") if p.strip()]
            invalid = [p for p in chosen if p not in PLANS]
            if invalid:
                print(f"Plan tidak dikenal: {invalid}. Pilihan: {list(PLANS)}")
                return 2
            config["plans"] = chosen

        saved = await set_watermark_config(db, config)
        print(json.dumps(saved, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
