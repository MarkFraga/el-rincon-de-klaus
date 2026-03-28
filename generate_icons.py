"""Generate PWA icons for El Rincon de Klaus."""
import os
from PIL import Image, ImageDraw, ImageFont

FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "assets")
os.makedirs(FRONTEND, exist_ok=True)

BG_COLOR = (26, 26, 46)       # #1a1a2e
ACCENT = (255, 107, 53)       # #ff6b35
DARK_BG = (10, 10, 10)        # #0a0a0a


def create_icon(size):
    img = Image.new("RGBA", (size, size), DARK_BG)
    draw = ImageDraw.Draw(img)

    # Background circle
    margin = int(size * 0.06)
    draw.ellipse([margin, margin, size - margin, size - margin], fill=BG_COLOR)

    # Inner accent ring
    ring_margin = int(size * 0.1)
    ring_width = max(2, int(size * 0.015))
    draw.ellipse(
        [ring_margin, ring_margin, size - ring_margin, size - ring_margin],
        outline=ACCENT, width=ring_width
    )

    cx, cy = size // 2, size // 2

    # Draw a stylized microphone using shapes
    # Mic head (rounded rectangle / ellipse)
    head_w = int(size * 0.18)
    head_h = int(size * 0.24)
    head_top = cy - int(size * 0.2)
    draw.rounded_rectangle(
        [cx - head_w, head_top, cx + head_w, head_top + head_h],
        radius=head_w,
        fill=ACCENT
    )

    # Mic body/stand line
    line_w = max(2, int(size * 0.03))
    body_top = head_top + head_h - 2
    body_bottom = cy + int(size * 0.12)
    draw.line(
        [(cx, body_top), (cx, body_bottom)],
        fill=ACCENT, width=line_w
    )

    # Mic arc (the U-shape around the head)
    arc_margin_x = int(size * 0.08)
    arc_w = head_w + int(size * 0.06)
    arc_top = head_top - int(size * 0.02)
    arc_bottom = head_top + head_h + int(size * 0.06)
    arc_lw = max(2, int(size * 0.025))
    draw.arc(
        [cx - arc_w, arc_top, cx + arc_w, arc_bottom],
        start=0, end=180,
        fill=ACCENT, width=arc_lw
    )

    # Base line
    base_y = body_bottom
    base_w = int(size * 0.12)
    draw.line(
        [(cx - base_w, base_y), (cx + base_w, base_y)],
        fill=ACCENT, width=line_w
    )

    # "K" letter at the bottom
    try:
        font_size = int(size * 0.13)
        font = ImageFont.truetype("arial.ttf", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()

    k_y = cy + int(size * 0.2)
    bbox = draw.textbbox((0, 0), "K", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((cx - tw // 2, k_y - th // 2), "K", fill=ACCENT, font=font)

    return img


for sz in [192, 512]:
    icon = create_icon(sz)
    path = os.path.join(FRONTEND, f"icon-{sz}.png")
    icon.save(path, "PNG")
    print(f"Created {path} ({sz}x{sz})")

print("Done!")
