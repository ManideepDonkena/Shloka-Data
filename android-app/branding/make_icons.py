"""Make every Android/Play icon and the splash screens from one artwork.

    /home/mani/shloka/venv/bin/python make_icons.py conch_full.svg      (an SVG with a <rect fill="url(#bg)"> background)
    /home/mani/shloka/venv/bin/python make_icons.py my_conch.png         (a PNG with a transparent background: it is placed
                                                                          on the saffron background with the chant waves)
Needs google-chrome (to draw SVG) and Pillow.
"""
import glob, os, re, subprocess, sys, tempfile
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "android", "app", "src", "main", "res")
OUT = os.path.join(HERE, "out")
BG_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000"><defs><radialGradient id="bg" cx="42%" cy="32%" r="85%"><stop offset="0" stop-color="#f39a3a"/><stop offset=".55" stop-color="#d65a20"/><stop offset="1" stop-color="#8f2414"/></radialGradient></defs><rect width="1000" height="1000" fill="url(#bg)"/><circle cx="500" cy="500" r="390" fill="none" stroke="#ffd9a0" stroke-opacity=".14" stroke-width="3"/></svg>"""
WAVES = """<g fill="none" stroke="#ffe7b0" stroke-linecap="round" transform="translate(830 250) rotate(-30)"><path d="M0 -36 q 34 36 0 72" stroke-width="20"/><path d="M42 -72 q 64 72 0 144" stroke-width="16" opacity=".72"/><path d="M84 -108 q 92 108 0 216" stroke-width="12" opacity=".45"/></g>"""


def chrome_png(svg_text, size, path):
    d = tempfile.mkdtemp()
    open(os.path.join(d, "a.svg"), "w").write(svg_text)
    open(os.path.join(d, "a.html"), "w").write(f'<html><body style="margin:0;background:transparent"><img src="a.svg" style="display:block;width:{size}px;height:{size}px"></body></html>')
    shot = os.path.join(d, "s.png")
    subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--default-background-color=00000000",
                    f"--window-size={size},{size + 200}", "--virtual-time-budget=3000", f"--screenshot={shot}", "file://" + os.path.join(d, "a.html")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    Image.open(shot).crop((0, 0, size, size)).save(path)
    return Image.open(path).convert("RGBA")


def layers(src):
    """(background 1000px, foreground 1000px with art inside the adaptive safe zone, full icon 1000px)"""
    bg = chrome_png(BG_SVG, 1000, os.path.join(OUT, "bg_1000.png"))
    if src.endswith(".svg"):
        s = open(src).read()
        full = chrome_png(s, 1000, os.path.join(OUT, "full_1000.png"))
        body = re.sub(r'<rect width="\d+" height="\d+" fill="url\(#bg\)"/>', "", s, count=1)
        body = re.sub(r'<circle[^>]*stroke-opacity="\.1\d"[^>]*/>', "", body)
        vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', s).group(1)
        c = int(vb) / 2
        body = re.sub(r"(<svg[^>]*>)", r'\1<g transform="translate(%g %g) scale(.7) translate(-%g -%g)">' % (c, c, c, c), body, count=1).replace("</svg>", "</g></svg>")
        fg = chrome_png(body, 1000, os.path.join(OUT, "fg_1000.png"))
    else:
        art = Image.open(src).convert("RGBA")
        art.thumbnail((640, 640), Image.LANCZOS)
        waves = chrome_png('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">' + WAVES + "</svg>", 1000, os.path.join(OUT, "waves.png"))
        def place(scale):
            layer = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
            a = art.resize((int(art.width * scale), int(art.height * scale)), Image.LANCZOS)
            layer.alpha_composite(a, ((1000 - a.width) // 2, (1000 - a.height) // 2 + 20))
            w = waves.resize((1000, 1000))
            return Image.alpha_composite(layer, w) if scale > 1 else layer
        full = Image.alpha_composite(bg, place(1.25))
        fg = place(0.95)
        full.save(os.path.join(OUT, "full_1000.png"))
        fg.save(os.path.join(OUT, "fg_1000.png"))
    return bg, fg, full


def masked(img, shape):
    s = img.size[0]
    m = Image.new("L", (s * 4, s * 4), 0)
    d = ImageDraw.Draw(m)
    if shape == "circle":
        d.ellipse((0, 0, s * 4 - 1, s * 4 - 1), fill=255)
    else:
        d.rounded_rectangle((0, 0, s * 4 - 1, s * 4 - 1), radius=int(s * 4 * 0.22), fill=255)
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    out.paste(img, (0, 0), m.resize((s, s), Image.LANCZOS))
    return out


def main(src):
    os.makedirs(OUT, exist_ok=True)
    bg, fg, full = layers(src)
    full.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "store_icon_512.png"))
    for k, f in {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}.items():
        a, l = round(108 * f), round(48 * f)
        fg.resize((a, a), Image.LANCZOS).save(f"{RES}/mipmap-{k}/ic_launcher_foreground.png")
        bg.resize((a, a), Image.LANCZOS).save(f"{RES}/mipmap-{k}/ic_launcher_background.png")
        ic = full.resize((l, l), Image.LANCZOS)
        masked(ic, "rr").save(f"{RES}/mipmap-{k}/ic_launcher.png")
        masked(ic, "circle").save(f"{RES}/mipmap-{k}/ic_launcher_round.png")
    for p in glob.glob(f"{RES}/drawable*/splash.png"):
        w, h = Image.open(p).size
        side = max(w, h)
        sp = bg.resize((side, side), Image.LANCZOS).crop(((side - w) // 2, (side - h) // 2, (side - w) // 2 + w, (side - h) // 2 + h))
        c = fg.resize((int(min(w, h) * 0.9),) * 2, Image.LANCZOS)
        sp.alpha_composite(c, ((w - c.width) // 2, (h - c.height) // 2))
        sp.convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(p, optimize=True)   # keeps the APK small
    comp = Image.alpha_composite(bg, fg).resize((432, 432), Image.LANCZOS)
    prev = Image.new("RGBA", (432 * 2 + 30, 432), (44, 44, 44, 255))
    prev.paste(masked(comp, "circle"), (0, 0), masked(comp, "circle"))
    prev.paste(masked(comp, "rr"), (462, 0), masked(comp, "rr"))
    prev.save(os.path.join(OUT, "adaptive_preview.png"))
    print("icons, store icon and splash screens written from", src)


if __name__ == "__main__":
    main(sys.argv[1])
