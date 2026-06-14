"""生成应用图标(packaging/appicon.icns + appicon.ico)。

本地一次性工具(在 macOS 上跑, 需要 Pillow + 系统自带 iconutil/sips):
    python packaging/make_icon.py
产物已提交进仓库, CI 打包直接用, 不在 CI 里重生成。
风格: 靛紫圆角方块 + 白色闪电, 和控制台内的品牌标一致。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
SIZE = 1024
TOP = (124, 92, 255)     # 靛
BOTTOM = (91, 75, 219)   # 紫
# 闪电多边形(相对整张画布 0..1, y 向下)
BOLT = [(0.560, 0.150), (0.335, 0.545), (0.485, 0.545),
        (0.445, 0.855), (0.675, 0.455), (0.520, 0.455)]


def _vgradient(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        d.line([(0, y), (size, y)],
               fill=tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)))
    return img


def _master() -> Image.Image:
    margin = int(SIZE * 0.085)
    inner = SIZE - 2 * margin
    radius = int(inner * 0.235)
    mask = Image.new("L", (inner, inner), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, inner - 1, inner - 1], radius=radius, fill=255)
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(_vgradient(inner), (margin, margin), mask)
    ImageDraw.Draw(icon).polygon([(SIZE * x, SIZE * y) for x, y in BOLT], fill=(255, 255, 255, 255))
    return icon


def main() -> int:
    master = _master()
    png = HERE / "appicon.png"
    master.save(png)
    print("wrote", png)

    # .ico (Windows)
    ico = HERE / "appicon.ico"
    master.save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", ico)

    # .icns (macOS), 需要 iconutil
    iconset = HERE / "appicon.iconset"
    iconset.mkdir(exist_ok=True)
    for base in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = base * scale
            name = f"icon_{base}x{base}{'@2x' if scale == 2 else ''}.png"
            master.resize((px, px), Image.Resampling.LANCZOS).save(iconset / name)
    try:
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "appicon.icns")],
                       check=True)
        print("wrote", HERE / "appicon.icns")
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"!! 跳过 .icns(无 iconutil, 非 macOS?): {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
