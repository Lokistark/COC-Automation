"""
Synthetic CoC Screenshot Generator.
Generates realistic Clash of Clans gameplay and enemy-base screenshots
for automated testing and visual demonstration when actual game captures are absent.
"""

import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def create_synthetic_screenshot(
    output_path: str,
    width: int = 1280,
    height: int = 720,
    mode: str = "village",  # "village" or "enemy_base"
    gold: int = 4250000,
    elixir: int = 3600000,
    dark_elixir: int = 98000,
    builders_free: int = 3,
    builders_total: int = 5,
    town_hall_level: int = 11
) -> str:
    """Generates a synthetic screenshot with realistic layout and HUD elements."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img = Image.new("RGB", (width, height), (34, 139, 34))  # Grass green background
    draw = ImageDraw.Draw(img)

    # 1. Background Grid / Terrain Texture
    # Alternating green checkerboard tiles for village base
    tile_size = int(min(width, height) / 20)
    for x in range(0, width, tile_size):
        for y in range(0, height, tile_size):
            if (x // tile_size + y // tile_size) % 2 == 0:
                draw.rectangle([x, y, x + tile_size, y + tile_size], fill=(42, 149, 42))

    # Center village boundary
    pad_x = int(width * 0.15)
    pad_y = int(height * 0.18)
    draw.rectangle([pad_x, pad_y, width - pad_x, height - pad_y], outline=(60, 160, 60), width=3)

    if mode == "enemy_base":
        # Red dashed deployment border around the base
        draw.rectangle([pad_x - 15, pad_y - 15, width - pad_x + 15, height - pad_y + 15], outline=(220, 40, 40), width=4)

    # 2. Draw Village Buildings & Defenses (Isometric boxes with labels)
    cx, cy = width // 2, height // 2

    # Town Hall in center
    th_w, th_h = int(width * 0.08), int(height * 0.10)
    draw.rectangle([cx - th_w, cy - th_h, cx + th_w, cy + th_h], fill=(139, 69, 19), outline=(218, 165, 32), width=3)
    draw.rectangle([cx - th_w + 5, cy - th_h + 5, cx + th_w - 5, cy - int(th_h * 0.4)], fill=(178, 34, 34))  # Red TH roof
    draw.text((cx - 30, cy - 10), f"TH {town_hall_level}", fill=(255, 255, 255))

    # Defenses & Storages
    structures = [
        # (name, offset_x, offset_y, color, border_color)
        ("Air Def 1", -int(width * 0.15), -int(height * 0.12), (180, 80, 50), (255, 215, 0)),
        ("Air Def 2", int(width * 0.15), -int(height * 0.12), (180, 80, 50), (255, 215, 0)),
        ("Air Def 3", -int(width * 0.15), int(height * 0.12), (180, 80, 50), (255, 215, 0)),
        ("Air Def 4", int(width * 0.15), int(height * 0.12), (180, 80, 50), (255, 215, 0)),
        ("Inferno 1", -int(width * 0.08), int(height * 0.02), (200, 40, 20), (255, 100, 0)),
        ("Inferno 2", int(width * 0.08), int(height * 0.02), (200, 40, 20), (255, 100, 0)),
        ("Eagle Art", 0, -int(height * 0.18), (80, 90, 110), (0, 200, 255)),
        ("Gold Stor", -int(width * 0.22), 0, (218, 165, 32), (255, 255, 0)),
        ("Elixir Stor", int(width * 0.22), 0, (186, 85, 211), (255, 0, 255)),
        ("Dark Stor", 0, int(height * 0.18), (47, 79, 79), (0, 255, 255)),
    ]

    for name, ox, oy, col, bcol in structures:
        bx, by = cx + ox, cy + oy
        bw, bh = int(width * 0.04), int(height * 0.06)
        draw.rectangle([bx - bw, by - bh, bx + bw, by + bh], fill=col, outline=bcol, width=2)
        draw.text((bx - 25, by - 6), name, fill=(255, 255, 255))

    # 3. Top HUD: Resources (Top-Right)
    hud_bg = (20, 24, 34, 210)
    res_x = int(width * 0.72)
    res_w = int(width * 0.26)
    res_h = int(height * 0.20)
    draw.rectangle([res_x, 10, res_x + res_w, 10 + res_h], fill=(20, 24, 34), outline=(70, 80, 100), width=2)

    # Gold Bar
    draw.rectangle([res_x + 10, 20, res_x + 30, 40], fill=(245, 158, 11))  # Coin icon
    draw.text((res_x + 40, 22), f"Gold: {gold:,}", fill=(255, 215, 0))

    # Elixir Bar
    draw.rectangle([res_x + 10, 50, res_x + 30, 70], fill=(217, 70, 239))  # Elixir icon
    draw.text((res_x + 40, 52), f"Elixir: {elixir:,}", fill=(232, 121, 249))

    # Dark Elixir Bar
    draw.rectangle([res_x + 10, 80, res_x + 30, 100], fill=(6, 182, 212))  # Dark Elixir icon
    draw.text((res_x + 40, 82), f"Dark: {dark_elixir:,}", fill=(56, 189, 248))

    # 4. Top-Center Builder Bar
    builder_w = int(width * 0.18)
    builder_x = int((width - builder_w) / 2)
    draw.rectangle([builder_x, 10, builder_x + builder_w, 45], fill=(30, 36, 50), outline=(80, 95, 120), width=2)
    draw.rectangle([builder_x + 8, 16, builder_x + 28, 38], fill=(245, 158, 11))  # Builder hammer
    draw.text((builder_x + 36, 18), f"Builders: {builders_free}/{builders_total}", fill=(255, 255, 255))

    # 5. Top-Left Player Profile Banner
    draw.rectangle([10, 10, int(width * 0.18), 50], fill=(25, 30, 42), outline=(60, 70, 90), width=2)
    draw.text((20, 18), f"Level 148  [TH {town_hall_level}]", fill=(100, 200, 255))

    # 6. Bottom Banner (Attack / Training HUD)
    bar_y = int(height * 0.88)
    draw.rectangle([0, bar_y, width, height], fill=(15, 20, 28))
    if mode == "village":
        draw.rectangle([int(width * 0.05), bar_y + 10, int(width * 0.18), height - 10], fill=(220, 38, 38), outline=(255, 255, 255), width=2)
        draw.text((int(width * 0.08), bar_y + 25), "ATTACK!", fill=(255, 255, 255))

        draw.rectangle([int(width * 0.22), bar_y + 10, int(width * 0.35), height - 10], fill=(37, 99, 235), outline=(255, 255, 255), width=2)
        draw.text((int(width * 0.25), bar_y + 25), "TRAIN TROOPS", fill=(255, 255, 255))
    else:
        draw.text((int(width * 0.05), bar_y + 25), "SCOUTING ENEMY BASE - TACTICAL OVERLAY ACTIVE", fill=(255, 100, 100))

    img.save(output_path, "JPEG", quality=90)
    return output_path
