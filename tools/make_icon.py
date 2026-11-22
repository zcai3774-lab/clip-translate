"""Generate the ClipTranslate app icon (PNG + multi-size Windows ICO)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "cliplens" / "assets"
SIZE = 1024


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("msyhbd.ttc", "msyh.ttc", "simhei.ttf"):
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _gradient(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size), "#10192B")
    top = (30, 50, 88)
    bottom = (8, 12, 22)
    for y in range(size):
        t = y / max(1, size - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        ImageDraw.Draw(image).line((0, y, size, y), fill=color)
    return image


def main() -> int:
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (28, 28, SIZE - 28, SIZE - 28), radius=224, fill=255
    )
    gradient = _gradient(SIZE).convert("RGBA")
    canvas.paste(gradient, (0, 0), mask)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (28, 28, SIZE - 28, SIZE - 28),
        radius=224,
        outline=(70, 104, 168, 255),
        width=5,
    )

    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        (150, 120, 880, 850), fill=(91, 140, 255, 52)
    )
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    canvas.alpha_composite(Image.composite(glow, Image.new("RGBA", (SIZE, SIZE)), mask))

    font = _font(470)
    text = "译"
    box = draw.textbbox((0, 0), text, font=font)
    x = (SIZE - (box[2] - box[0])) / 2 - box[0]
    y = (SIZE - (box[3] - box[1])) / 2 - box[1] - 10
    draw.text((x, y), text, font=font, fill=(232, 240, 255, 255))

    # Small green status dot, the same accent used in the app header.
    draw.ellipse(
        (714, 714, 846, 846),
        fill=(84, 224, 166, 255),
        outline=(16, 30, 26, 255),
        width=14,
    )

    final = canvas.resize((512, 512), Image.Resampling.LANCZOS)
    ASSETS.mkdir(parents=True, exist_ok=True)
    png = ASSETS / "icon.png"
    final.save(png, format="PNG", optimize=True)
    ico = ASSETS / "icon.ico"
    final.save(
        ico,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"wrote {png} ({png.stat().st_size} bytes)")
    print(f"wrote {ico} ({ico.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
