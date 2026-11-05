"""Turn a traced conch SVG (drawn on a black background) into a transparent PNG for make_icons.py.

    /home/mani/shloka/venv/bin/python prep_traced.py conch_traced.svg      -> conch_traced.png

What it does:
  * drops every path filled pure black (#000000): the full-canvas background and the tiny black specks
  * turns the pale pink tracing tints (#F1D7EB, #E9CFE9, ...) into the shell's warm white
  * renders it with Chrome, makes any leftover near-black pixels transparent, and crops tight to the shell
"""
import os, re, sys
from PIL import Image
from make_icons import chrome_png

PINK_TO_WHITE = {"#F1D7EB": "#FBF6EE", "#E9CFE9": "#F4EEE6", "#FBF8FA": "#FFFDF9"}


def main(src):
    s = open(src).read()
    n0 = len(re.findall(r"<path", s))
    s = re.sub(r'<path[^>]*fill="#000000"[^>]*>\s*</path>', "", s, flags=re.S)
    s = re.sub(r'<path[^>]*fill="#000000"[^>]*/>', "", s, flags=re.S)
    for a, b in PINK_TO_WHITE.items():
        s = s.replace(f'fill="{a}"', f'fill="{b}"')
    print(f"paths: {n0} -> {len(re.findall(r'<path', s))} (black removed)")
    out_png = os.path.splitext(src)[0] + ".png"
    img = chrome_png(s, 2048, out_png)
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a and r < 40 and g < 40 and b < 40:
                px[x, y] = (0, 0, 0, 0)
    box = img.getbbox()
    img = img.crop(box)
    pad = int(max(img.size) * 0.02)
    sq = max(img.size) + 2 * pad
    canvas = Image.new("RGBA", (sq, sq), (0, 0, 0, 0))
    canvas.alpha_composite(img, ((sq - img.width) // 2, (sq - img.height) // 2))
    canvas.save(out_png)
    print("wrote", out_png, canvas.size)
    return out_png


if __name__ == "__main__":
    main(sys.argv[1])
