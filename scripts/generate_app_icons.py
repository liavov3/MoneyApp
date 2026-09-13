"""Rebuild the simple MoneySaver wallet icon (Pillow; assets are committed)."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / "mobile" / "public" / "icons"
root.mkdir(parents=True, exist_ok=True)
scale = 4
canvas = Image.new("RGB", (512 * scale, 512 * scale), "#0B0E13")
draw = ImageDraw.Draw(canvas)


def box(values):
    return tuple(round(value * scale) for value in values)


draw.rounded_rectangle(box((108, 140, 400, 366)), radius=38 * scale, fill="#5B8DEF")
draw.rounded_rectangle(box((108, 136, 384, 189)), radius=26 * scale, fill="#8AAFF5")
draw.rounded_rectangle(box((287, 228, 415, 309)), radius=23 * scale, fill="#1E2A44")
draw.ellipse(box((314, 254, 340, 280)), fill="#F5F7FA")
draw.line([box((157, 282)), box((183, 307)), box((237, 247))], fill="#0B0E13", width=18 * scale, joint="curve")
for filename, size in [("icon-192.png", 192), ("icon-512.png", 512),
                       ("icon-maskable-512.png", 512), ("apple-touch-icon.png", 180)]:
    canvas.resize((size, size), Image.Resampling.LANCZOS).save(root / filename, optimize=True)
print("Created four MoneySaver installation icons.")
