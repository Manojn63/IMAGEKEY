"""Generate luxury 3D Champagne Gold & Deep Obsidian Brand Logo and APK App Icons."""

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

def create_luxury_logo():
    size = 1024
    img = Image.new("RGBA", (size, size), (10, 13, 20, 255)) # Deep Obsidian #0A0D14
    draw = ImageDraw.Draw(img)

    center = size // 2
    
    # Outer luxury gold glow
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        [center - 420, center - 420, center + 420, center + 420],
        fill=(212, 175, 55, 30) # Champagne gold glow
    )
    glow = glow.filter(ImageFilter.GaussianBlur(32))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # 1. Beveled Octagonal / Rounded Shield Ring (Champagne Gold)
    outer_r = 380
    draw.ellipse(
        [center - outer_r, center - outer_r, center + outer_r, center + outer_r],
        fill=(18, 24, 38, 255),
        outline=(212, 175, 55, 255), # Champagne gold #D4AF37
        width=18
    )

    # Inner decorative gold ring
    inner_gold_r = 340
    draw.ellipse(
        [center - inner_gold_r, center - inner_gold_r, center + inner_gold_r, center + inner_gold_r],
        outline=(229, 193, 88, 200), # Lighter champagne gold #E5C158
        width=6
    )

    # Optical Vault Aperture Inner Plate (Deep Obsidian)
    plate_r = 310
    draw.ellipse(
        [center - plate_r, center - plate_r, center + plate_r, center + plate_r],
        fill=(10, 13, 20, 255),
        outline=(16, 185, 129, 180), # Emerald green accent ring #10B981
        width=8
    )

    # 2. Four Optical HUD Corner Brackets in Champagne Gold
    bracket_len = 70
    bracket_width = 8
    gold_accent = (229, 193, 88, 255)
    
    # Top-Left Bracket
    draw.line([(center - 220, center - 160), (center - 220, center - 220)], fill=gold_accent, width=bracket_width)
    draw.line([(center - 220, center - 220), (center - 160, center - 220)], fill=gold_accent, width=bracket_width)
    
    # Top-Right Bracket
    draw.line([(center + 220, center - 160), (center + 220, center - 220)], fill=gold_accent, width=bracket_width)
    draw.line([(center + 220, center - 220), (center + 160, center - 220)], fill=gold_accent, width=bracket_width)

    # Bottom-Left Bracket
    draw.line([(center - 220, center + 160), (center - 220, center + 220)], fill=gold_accent, width=bracket_width)
    draw.line([(center - 220, center + 220), (center - 160, center + 220)], fill=gold_accent, width=bracket_width)

    # Bottom-Right Bracket
    draw.line([(center + 220, center + 160), (center + 220, center + 220)], fill=gold_accent, width=bracket_width)
    draw.line([(center + 220, center + 220), (center + 160, center + 220)], fill=gold_accent, width=bracket_width)

    # 3. Emerald Laser Scanner Sweep Line
    laser_y = center - 40
    laser_overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    laser_draw = ImageDraw.Draw(laser_overlay)
    laser_draw.line(
        [(center - 240, laser_y), (center + 240, laser_y)],
        fill=(16, 185, 129, 230),
        width=10
    )
    laser_overlay = laser_overlay.filter(ImageFilter.GaussianBlur(4))
    img = Image.alpha_composite(img, laser_overlay)
    draw = ImageDraw.Draw(img)
    draw.line(
        [(center - 230, laser_y), (center + 230, laser_y)],
        fill=(255, 255, 255, 240),
        width=3
    )

    # 4. Central Optical Lens & Vault Key Emblem (Gold + Emerald)
    # Key Bow / Iris Outer Ring
    key_center_y = center - 30
    draw.ellipse(
        [center - 110, key_center_y - 110, center + 110, key_center_y + 110],
        fill=(212, 175, 55, 255),
        outline=(243, 229, 171, 255),
        width=10
    )
    # Lens Aperture
    draw.ellipse(
        [center - 70, key_center_y - 70, center + 70, key_center_y + 70],
        fill=(10, 13, 20, 255),
        outline=(16, 185, 129, 255),
        width=8
    )
    # Emerald pupil reflection
    draw.ellipse(
        [center - 32, key_center_y - 32, center + 32, key_center_y + 32],
        fill=(16, 185, 129, 255)
    )
    draw.ellipse(
        [center - 12, key_center_y - 18, center + 6, key_center_y],
        fill=(255, 255, 255, 240)
    )

    # 5. Vertical Key Shaft (Champagne Gold)
    shaft_top = key_center_y + 85
    shaft_bottom = center + 250
    shaft_w = 34
    draw.rounded_rectangle(
        [center - shaft_w//2, shaft_top, center + shaft_w//2, shaft_bottom],
        radius=8,
        fill=(212, 175, 55, 255),
        outline=(243, 229, 171, 255),
        width=4
    )

    # 6. Optical Key Bitting / Ward Teeth (Champagne Gold)
    # Top bit
    draw.rounded_rectangle(
        [center + shaft_w//2 - 2, center + 140, center + shaft_w//2 + 56, center + 172],
        radius=6,
        fill=(212, 175, 55, 255),
        outline=(243, 229, 171, 255),
        width=3
    )
    # Bottom bit
    draw.rounded_rectangle(
        [center + shaft_w//2 - 2, center + 195, center + shaft_w//2 + 42, center + 227],
        radius=6,
        fill=(212, 175, 55, 255),
        outline=(243, 229, 171, 255),
        width=3
    )

    # Save Master Logo
    img_dir = Path("app/static/img")
    img_dir.mkdir(parents=True, exist_ok=True)
    
    logo_path = img_dir / "logo.png"
    img.save(logo_path, format="PNG", quality=100)
    print(f"Saved master logo: {logo_path} ({size}x{size})")

    # Generate 512x512 APK Icon
    icon_512 = img.resize((512, 512), Image.Resampling.LANCZOS)
    icon_512_path = img_dir / "icon-512.png"
    icon_512.save(icon_512_path, format="PNG", quality=95)
    print(f"Saved APK icon: {icon_512_path} (512x512)")

    # Generate 192x192 APK Icon
    icon_192 = img.resize((192, 192), Image.Resampling.LANCZOS)
    icon_192_path = img_dir / "icon-192.png"
    icon_192.save(icon_192_path, format="PNG", quality=95)
    print(f"Saved APK icon: {icon_192_path} (192x192)")

if __name__ == "__main__":
    create_luxury_logo()
