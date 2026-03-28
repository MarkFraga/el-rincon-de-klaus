"""
Generate a cartoon avatar for KLAUS - the crazy old man podcast host.
"""

from PIL import Image, ImageDraw, ImageFont
import math


def draw_ellipse_outline(draw, bbox, fill, outline, width=2):
    """Draw an ellipse with outline."""
    draw.ellipse(bbox, fill=fill, outline=outline, width=width)


def generate_klaus_avatar():
    W, H = 512, 512
    img = Image.new("RGBA", (W, H), (30, 30, 40, 255))  # dark background
    draw = ImageDraw.Draw(img)

    # --- BODY (dark suit, slightly hunched) ---
    # Torso - shifted slightly right to give hunched feel
    body_color = (40, 40, 55)
    body_outline = (20, 20, 30)

    # Shoulders and torso
    draw.polygon([
        (140, 380), (160, 340), (200, 310), (256, 300),
        (312, 310), (352, 340), (372, 380),
        (380, 512), (132, 512)
    ], fill=body_color, outline=body_outline)

    # Suit lapels
    lapel_color = (55, 55, 70)
    # Left lapel
    draw.polygon([
        (200, 310), (256, 300), (240, 400), (195, 370)
    ], fill=lapel_color, outline=body_outline)
    # Right lapel
    draw.polygon([
        (256, 300), (312, 310), (317, 370), (272, 400)
    ], fill=lapel_color, outline=body_outline)

    # Shirt/tie area
    draw.polygon([
        (240, 300), (256, 295), (272, 300), (268, 400), (244, 400)
    ], fill=(200, 200, 210))
    # Tie
    draw.polygon([
        (250, 310), (262, 310), (260, 380), (252, 380)
    ], fill=(140, 30, 30))

    # Suit buttons
    draw.ellipse([251, 400, 261, 410], fill=(80, 80, 90))
    draw.ellipse([251, 425, 261, 435], fill=(80, 80, 90))

    # --- HEAD ---
    head_cx, head_cy = 256, 200
    head_rx, head_ry = 88, 100

    # Head shape (skin color)
    skin = (235, 200, 170)
    skin_outline = (60, 40, 30)

    draw.ellipse(
        [head_cx - head_rx, head_cy - head_ry, head_cx + head_rx, head_cy + head_ry],
        fill=skin, outline=skin_outline, width=3
    )

    # --- EARS ---
    ear_w, ear_h = 22, 30
    # Left ear
    draw.ellipse(
        [head_cx - head_rx - ear_w + 5, head_cy - 10,
         head_cx - head_rx + 10, head_cy - 10 + ear_h * 2],
        fill=skin, outline=skin_outline, width=2
    )
    # Right ear
    draw.ellipse(
        [head_cx + head_rx - 10, head_cy - 10,
         head_cx + head_rx + ear_w - 5, head_cy - 10 + ear_h * 2],
        fill=skin, outline=skin_outline, width=2
    )

    # --- BALD HEAD (shiny) ---
    # Highlight on top of head
    draw.ellipse(
        [head_cx - 40, head_cy - head_ry + 5, head_cx + 30, head_cy - head_ry + 45],
        fill=(245, 220, 195)
    )
    # Smaller shine
    draw.ellipse(
        [head_cx - 20, head_cy - head_ry + 10, head_cx + 10, head_cy - head_ry + 30],
        fill=(255, 235, 215)
    )

    # --- TWO HAIRS sticking up comically ---
    hair_color = (180, 180, 180)
    hair_outline_color = (60, 60, 60)

    # Hair 1 - left, curving left
    hair1_points = []
    for t in range(0, 101, 2):
        tt = t / 100.0
        x = head_cx - 20 + (-30) * tt + 10 * math.sin(tt * math.pi * 2)
        y = (head_cy - head_ry + 10) - 60 * tt + 5 * math.sin(tt * math.pi * 3)
        hair1_points.append((x, y))
    # Draw as thick line
    for i in range(len(hair1_points) - 1):
        draw.line([hair1_points[i], hair1_points[i + 1]], fill=hair_outline_color, width=5)
    for i in range(len(hair1_points) - 1):
        draw.line([hair1_points[i], hair1_points[i + 1]], fill=hair_color, width=3)

    # Hair 2 - right, curving right
    hair2_points = []
    for t in range(0, 101, 2):
        tt = t / 100.0
        x = head_cx + 15 + (25) * tt + 8 * math.sin(tt * math.pi * 2.5)
        y = (head_cy - head_ry + 10) - 55 * tt + 7 * math.sin(tt * math.pi * 2)
        hair2_points.append((x, y))
    for i in range(len(hair2_points) - 1):
        draw.line([hair2_points[i], hair2_points[i + 1]], fill=hair_outline_color, width=5)
    for i in range(len(hair2_points) - 1):
        draw.line([hair2_points[i], hair2_points[i + 1]], fill=hair_color, width=3)

    # Little curl at end of each hair
    last1 = hair1_points[-1]
    draw.ellipse([last1[0] - 5, last1[1] - 5, last1[0] + 5, last1[1] + 5],
                 fill=hair_color, outline=hair_outline_color, width=2)
    last2 = hair2_points[-1]
    draw.ellipse([last2[0] - 5, last2[1] - 5, last2[0] + 5, last2[1] + 5],
                 fill=hair_color, outline=hair_outline_color, width=2)

    # --- EYEBROWS (bushy, wild) ---
    brow_color = (200, 200, 200)
    # Left eyebrow - raised high (surprised/crazy look)
    draw.polygon([
        (195, 160), (200, 148), (240, 142), (245, 152), (238, 158), (205, 162)
    ], fill=brow_color, outline=skin_outline, width=2)
    # Right eyebrow - lower, angled differently
    draw.polygon([
        (267, 155), (270, 147), (308, 152), (312, 162), (305, 165), (272, 160)
    ], fill=brow_color, outline=skin_outline, width=2)

    # --- EYES (crazy/schizophrenic - wide open, different directions) ---
    eye_white = (255, 255, 255)

    # Left eye - wide open (big for crazy look)
    left_eye_cx, left_eye_cy = 216, 185
    left_eye_rx, left_eye_ry = 27, 25
    draw.ellipse(
        [left_eye_cx - left_eye_rx, left_eye_cy - left_eye_ry,
         left_eye_cx + left_eye_rx, left_eye_cy + left_eye_ry],
        fill=eye_white, outline=(40, 30, 30), width=3
    )

    # Right eye - wide open (big for crazy look)
    right_eye_cx, right_eye_cy = 296, 185
    right_eye_rx, right_eye_ry = 27, 25
    draw.ellipse(
        [right_eye_cx - right_eye_rx, right_eye_cy - right_eye_ry,
         right_eye_cx + right_eye_rx, right_eye_cy + right_eye_ry],
        fill=eye_white, outline=(40, 30, 30), width=3
    )

    # Bloodshot lines in eyes - thick and visible
    bloodshot = (220, 40, 40)
    bloodshot_light = (240, 80, 80)
    # Left eye bloodshot
    for angle_deg in [15, 55, 100, 145, 200, 250, 300, 340]:
        a = math.radians(angle_deg)
        x1 = left_eye_cx + (left_eye_rx - 12) * math.cos(a)
        y1 = left_eye_cy + (left_eye_ry - 12) * math.sin(a)
        x2 = left_eye_cx + (left_eye_rx - 2) * math.cos(a)
        y2 = left_eye_cy + (left_eye_ry - 2) * math.sin(a)
        draw.line([(x1, y1), (x2, y2)], fill=bloodshot, width=2)
        # Branch
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        branch_a = math.radians(angle_deg + 30)
        bx = mid_x + 4 * math.cos(branch_a)
        by = mid_y + 4 * math.sin(branch_a)
        draw.line([(mid_x, mid_y), (bx, by)], fill=bloodshot_light, width=1)
    # Right eye bloodshot
    for angle_deg in [10, 60, 110, 160, 210, 260, 305, 350]:
        a = math.radians(angle_deg)
        x1 = right_eye_cx + (right_eye_rx - 12) * math.cos(a)
        y1 = right_eye_cy + (right_eye_ry - 12) * math.sin(a)
        x2 = right_eye_cx + (right_eye_rx - 2) * math.cos(a)
        y2 = right_eye_cy + (right_eye_ry - 2) * math.sin(a)
        draw.line([(x1, y1), (x2, y2)], fill=bloodshot, width=2)
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        branch_a = math.radians(angle_deg - 25)
        bx = mid_x + 4 * math.cos(branch_a)
        by = mid_y + 4 * math.sin(branch_a)
        draw.line([(mid_x, mid_y), (bx, by)], fill=bloodshot_light, width=1)

    # Irises - BLUE, looking in different directions!
    iris_color = (40, 120, 220)
    iris_outline = (20, 50, 120)
    iris_r = 12

    # Left eye iris - looking UP-LEFT (exaggerated)
    left_iris_cx = left_eye_cx - 10
    left_iris_cy = left_eye_cy - 9
    draw.ellipse(
        [left_iris_cx - iris_r, left_iris_cy - iris_r,
         left_iris_cx + iris_r, left_iris_cy + iris_r],
        fill=iris_color, outline=iris_outline, width=2
    )

    # Right eye iris - looking DOWN-RIGHT (exaggerated)
    right_iris_cx = right_eye_cx + 10
    right_iris_cy = right_eye_cy + 9
    draw.ellipse(
        [right_iris_cx - iris_r, right_iris_cy - iris_r,
         right_iris_cx + iris_r, right_iris_cy + iris_r],
        fill=iris_color, outline=iris_outline, width=2
    )

    # Pupils - small, intense black dots
    pupil_r = 5
    # Left pupil (in iris)
    draw.ellipse(
        [left_iris_cx - pupil_r, left_iris_cy - pupil_r,
         left_iris_cx + pupil_r, left_iris_cy + pupil_r],
        fill=(10, 10, 10)
    )
    # Tiny white reflection
    draw.ellipse(
        [left_iris_cx - 2, left_iris_cy - 3, left_iris_cx + 1, left_iris_cy - 1],
        fill=(255, 255, 255)
    )
    # Right pupil
    draw.ellipse(
        [right_iris_cx - pupil_r, right_iris_cy - pupil_r,
         right_iris_cx + pupil_r, right_iris_cy + pupil_r],
        fill=(10, 10, 10)
    )
    draw.ellipse(
        [right_iris_cx - 2, right_iris_cy - 3, right_iris_cx + 1, right_iris_cy - 1],
        fill=(255, 255, 255)
    )

    # --- WRINKLES ---
    wrinkle_color = (200, 170, 140)
    # Under eyes
    draw.arc([left_eye_cx - 20, left_eye_cy + 15, left_eye_cx + 20, left_eye_cy + 30],
             0, 180, fill=wrinkle_color, width=1)
    draw.arc([right_eye_cx - 20, right_eye_cy + 15, right_eye_cx + 20, right_eye_cy + 30],
             0, 180, fill=wrinkle_color, width=1)
    # Forehead wrinkles
    for y_off in [0, 10, 20]:
        draw.arc([head_cx - 50, head_cy - 80 + y_off, head_cx + 50, head_cy - 60 + y_off],
                 10, 170, fill=wrinkle_color, width=1)
    # Crow's feet
    for dy in [-3, 0, 3]:
        draw.line([(left_eye_cx - left_eye_rx - 2, left_eye_cy + dy),
                   (left_eye_cx - left_eye_rx - 12, left_eye_cy + dy - 5)],
                  fill=wrinkle_color, width=1)
        draw.line([(right_eye_cx + right_eye_rx + 2, right_eye_cy + dy),
                   (right_eye_cx + right_eye_rx + 12, right_eye_cy + dy - 5)],
                  fill=wrinkle_color, width=1)

    # --- BIG RED CLOWN NOSE ---
    nose_cx, nose_cy = 256, 220
    nose_r = 22
    # Shadow
    draw.ellipse(
        [nose_cx - nose_r + 3, nose_cy - nose_r + 3,
         nose_cx + nose_r + 3, nose_cy + nose_r + 3],
        fill=(120, 20, 20)
    )
    # Main nose
    draw.ellipse(
        [nose_cx - nose_r, nose_cy - nose_r, nose_cx + nose_r, nose_cy + nose_r],
        fill=(230, 40, 40), outline=(160, 20, 20), width=3
    )
    # Shine on nose
    draw.ellipse(
        [nose_cx - 10, nose_cy - 14, nose_cx + 2, nose_cy - 6],
        fill=(255, 120, 120)
    )
    draw.ellipse(
        [nose_cx - 6, nose_cy - 12, nose_cx - 2, nose_cy - 8],
        fill=(255, 180, 180)
    )

    # --- MOUTH (slightly open, goofy grin) ---
    # Draw a smile/grin under the beard area, just a hint visible
    draw.arc([head_cx - 30, 235, head_cx + 30, 265], 0, 180, fill=(150, 60, 60), width=3)

    # --- WHITE BEARD (full, messy) ---
    beard_color = (240, 240, 245)
    beard_shadow = (200, 200, 210)
    beard_outline_c = (140, 140, 150)

    # Main beard shape - big and bushy
    beard_points = []
    # Generate bushy beard outline
    for angle_deg in range(0, 361, 5):
        a = math.radians(angle_deg)
        # Base ellipse for beard
        base_x = head_cx + 80 * math.cos(a)
        base_y = 260 + 75 * math.sin(a)
        # Add randomish bumps for messy look
        bump = 8 * math.sin(angle_deg * 0.15) + 5 * math.sin(angle_deg * 0.3)
        # Only show bottom half of beard
        if math.sin(a) >= -0.3:
            beard_points.append((base_x + bump * math.cos(a), base_y + bump * math.sin(a)))
        else:
            beard_points.append((base_x, 240))

    draw.polygon(beard_points, fill=beard_color, outline=beard_outline_c, width=2)

    # Beard texture - wavy lines
    for i in range(8):
        x_start = head_cx - 55 + i * 15
        points = []
        for y in range(255, 330, 3):
            wave = 4 * math.sin((y - 255) * 0.15 + i * 0.7)
            points.append((x_start + wave, y))
        if len(points) > 1:
            draw.line(points, fill=beard_shadow, width=1)

    # Mustache
    draw.arc([head_cx - 45, 225, head_cx - 5, 260], 200, 360, fill=beard_outline_c, width=3)
    draw.arc([head_cx + 5, 225, head_cx + 45, 260], 180, 340, fill=beard_outline_c, width=3)

    # Beard highlight
    draw.ellipse([head_cx - 25, 260, head_cx + 25, 290], fill=(250, 250, 255))

    # --- NECK ---
    draw.rectangle([head_cx - 20, head_cy + head_ry - 10, head_cx + 20, 320], fill=skin)

    # --- Collar ---
    draw.polygon([
        (head_cx - 35, 300), (head_cx, 285), (head_cx + 35, 300),
        (head_cx + 30, 320), (head_cx, 310), (head_cx - 30, 320)
    ], fill=(230, 230, 240), outline=(180, 180, 190), width=2)

    # --- Final touches: redraw nose on top to ensure visibility ---
    # (beard may have overlapped)
    # Shadow
    draw.ellipse(
        [nose_cx - nose_r + 3, nose_cy - nose_r + 3,
         nose_cx + nose_r + 3, nose_cy + nose_r + 3],
        fill=(120, 20, 20)
    )
    draw.ellipse(
        [nose_cx - nose_r, nose_cy - nose_r, nose_cx + nose_r, nose_cy + nose_r],
        fill=(230, 40, 40), outline=(160, 20, 20), width=3
    )
    draw.ellipse(
        [nose_cx - 10, nose_cy - 14, nose_cx + 2, nose_cy - 6],
        fill=(255, 120, 120)
    )
    draw.ellipse(
        [nose_cx - 6, nose_cy - 12, nose_cx - 2, nose_cy - 8],
        fill=(255, 180, 180)
    )

    # Save
    output_path = r"C:\Users\marka\klaus-podcast\frontend\assets\klaus-avatar.png"
    img.save(output_path, "PNG")
    print(f"Avatar saved to: {output_path}")
    print(f"Image size: {img.size}")


if __name__ == "__main__":
    generate_klaus_avatar()
