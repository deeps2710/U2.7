from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "assets" / "ultron-logo.png"
DEFAULT_ICON = ROOT / "assets" / "ultron.ico"
DEFAULT_WEB_LOGO = ROOT / "web" / "ultron-logo.png"
DEFAULT_FAVICON = ROOT / "web" / "favicon.png"


def generate_assets(source: Path, icon: Path, web_logo: Path, favicon: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"ULTRON logo source was not found: {source}")
    with Image.open(source) as loaded:
        image = ImageOps.fit(loaded.convert("RGBA"), (1024, 1024), method=Image.Resampling.LANCZOS)

    icon.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        icon,
        format="ICO",
        sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    web_logo.parent.mkdir(parents=True, exist_ok=True)
    image.resize((256, 256), Image.Resampling.LANCZOS).save(web_logo, format="PNG", optimize=True)

    favicon.parent.mkdir(parents=True, exist_ok=True)
    image.resize((64, 64), Image.Resampling.LANCZOS).save(favicon, format="PNG", optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ULTRON desktop and web icons from the approved logo")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_ICON)
    parser.add_argument("--web-logo", type=Path, default=DEFAULT_WEB_LOGO)
    parser.add_argument("--favicon", type=Path, default=DEFAULT_FAVICON)
    args = parser.parse_args()
    generate_assets(args.source, args.output, args.web_logo, args.favicon)
    print(f"Generated {args.output.resolve()}")
    print(f"Generated {args.web_logo.resolve()}")
    print(f"Generated {args.favicon.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
