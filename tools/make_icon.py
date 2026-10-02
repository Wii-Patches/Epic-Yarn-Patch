#!/usr/bin/env python3
"""Turn assets/key-source.png (the Kirby's Epic Yarn logo) into the app icon.

  assets/icon.png   1024x1024, transparent, padded to a square
  assets/icon.ico   Windows, multi-size
  assets/icon.icns  macOS (needs `iconutil`, macOS only)
"""
import os, shutil, subprocess, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'assets')
SRC = os.path.join(OUT, 'key-source.png')
SIZE = 1024
PAD_FRACTION = 0.90          # the logo fills this fraction of the square canvas


def main():
    img = Image.open(SRC).convert('RGBA')
    box = img.getbbox()
    if box:
        img = img.crop(box)
    k = SIZE * PAD_FRACTION / max(img.size)
    img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    canvas = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(img, ((SIZE - img.width) // 2, (SIZE - img.height) // 2), img)
    png = os.path.join(OUT, 'icon.png')
    canvas.save(png)
    canvas.save(os.path.join(OUT, 'icon.ico'), sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)])
    if shutil.which('iconutil'):
        iconset = os.path.join(OUT, 'icon.iconset')
        shutil.rmtree(iconset, ignore_errors=True)
        os.makedirs(iconset)
        for s in (16, 32, 128, 256, 512):
            canvas.resize((s, s), Image.LANCZOS).save(os.path.join(iconset, 'icon_%dx%d.png' % (s, s)))
            canvas.resize((s * 2, s * 2), Image.LANCZOS).save(os.path.join(iconset, 'icon_%dx%d@2x.png' % (s, s)))
        subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', os.path.join(OUT, 'icon.icns')], check=True)
        shutil.rmtree(iconset)
    print('wrote', ', '.join(sorted(f for f in os.listdir(OUT) if f.startswith('icon'))))


if __name__ == '__main__':
    sys.exit(main())
