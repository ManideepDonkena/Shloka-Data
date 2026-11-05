"""Draw the Pāñcajanya conch as an SVG, laid out along its axis so every gold crown sits exactly on its whorl's edge.

    python draw_conch.py            -> conch_full.svg (icon with background + waves)

The shell is built in (u, v): u runs along the axis from the apex (u=0) to the tail, v across it (+v is the lip side).
Each whorl's top edge is one scalloped curve; the white fill and the gold rim are drawn from the *same* points.
"""
import math, os

HERE = os.path.dirname(os.path.abspath(__file__))
APEX, TAIL = (770.0, 120.0), (150.0, 880.0)
L = math.dist(APEX, TAIL)
D = ((TAIL[0] - APEX[0]) / L, (TAIL[1] - APEX[1]) / L)   # along the axis, apex -> tail
N = (-D[1], D[0])                                           # across the axis
if N[0] < 0:
    N = (-N[0], -N[1])                                      # +v points to the right/down: the lip side


def P(u, v):
    return (APEX[0] + D[0] * u + N[0] * v, APEX[1] + D[1] * u + N[1] * v)


def f(p):
    return f"{p[0]:.1f} {p[1]:.1f}"


SUTURES = [14, 62, 126, 208, 310, 432]          # u of each whorl's top edge; the last one is the body whorl
def w_spire(u):
    return 0.40 * u + 6


def crown(u0, w, n=None, h=None, bow=None):
    """Scalloped top edge from -w to +w at u0: base points + bump control points (bumps toward the apex)."""
    n = n or max(3, round(2 * w / 34))
    h = h if h is not None else min(22, 6 + w * 0.09)
    bow = bow if bow is not None else 0.16 * w
    pts = []
    for k in range(n + 1):
        t = -1 + 2 * k / n
        pts.append((u0 + bow * (1 - t * t), t * w))
    ctrl = []
    for k in range(n):
        (ua, va), (ub, vb) = pts[k], pts[k + 1]
        ctrl.append(((ua + ub) / 2 - 2 * h, (va + vb) / 2))
    return pts, ctrl


def crown_d(pts, ctrl, start=True):
    d = (f"M{f(P(*pts[0]))}" if start else f"L{f(P(*pts[0]))}")
    for c, p in zip(ctrl, pts[1:]):
        d += f" Q{f(P(*c))} {f(P(*p))}"
    return d


def whorl(u0, u1):
    w0, w1 = 1.22 * w_spire(u0) + 4, w_spire(u1 + 18)
    pts, ctrl = crown(u0, w0)
    d = crown_d(pts, ctrl)
    # right side down, bottom edge (bowed, hidden mostly by the next whorl), left side up
    d += f" C{f(P(u0 + 0.4 * (u1 - u0), w0 + 2))} {f(P(u1, w1 + 4))} {f(P(u1 + 18, w1))}"
    d += f" Q{f(P(u1 + 18 + 0.5 * (1.22 * w_spire(u1) + 4) * 0.16 * 2 + 30, 0))} {f(P(u1 + 18, -w1))}"  # base bows down under the next crown
    d += f" C{f(P(u1, -w1 - 4))} {f(P(u0 + 0.4 * (u1 - u0), -w0 - 2))} {f(P(*pts[0]))} Z"
    return d, crown_d(pts, ctrl)


def body():
    u0 = SUTURES[-1]
    w0 = 1.22 * w_spire(u0) + 4
    pts, ctrl = crown(u0, w0, n=8, h=20)
    d = crown_d(pts, ctrl)
    # right side runs a little way then hides under the lip
    d += f" C{f(P(u0 + 40, w0 + 20))} {f(P(u0 + 120, w0 - 10))} {f(P(u0 + 200, 40))}"
    # down the axis to the siphonal tail
    d += f" C{f(P(u0 + 330, 20))} {f(P(L - 140, 12))} {f(P(L, 0))}"
    # back up the left (outer, convex) side of the body whorl
    d += f" C{f(P(L - 160, -30))} {f(P(u0 + 360, -150))} {f(P(u0 + 200, -w0 - 50))}"
    d += f" C{f(P(u0 + 110, -w0 - 60))} {f(P(u0 + 30, -w0 - 20))} {f(P(*pts[0]))} Z"
    return d, crown_d(pts, ctrl)


def lip():
    """The flared aperture lip on the +v side with a wavy gold outer edge."""
    a, b = SUTURES[-1] + 6, L - 120            # where it leaves the body and where it rejoins near the tail
    outer = []
    n = 9
    for k in range(n + 1):
        t = k / n
        u = a + (b - a) * t
        v = w_spire(SUTURES[-1]) * 1.1 + 200 * math.sin(math.pi * t ** 0.65) * (1 - 0.55 * t) - 120 * t * t
        outer.append((u, v))
    d = f"M{f(P(a, 60))} C{f(P(a - 10, 120))} {f(P(a - 4, 150))} {f(P(*outer[0]))}"
    for k in range(n):
        (ua, va), (ub, vb) = outer[k], outer[k + 1]
        mu, mv = (ua + ub) / 2, (va + vb) / 2
        d += f" Q{f(P(mu, mv + 34))} {f(P(ub, vb))}"
    inner = f" C{f(P(b + 30, 20))} {f(P(b - 120, 8))} {f(P(b - 200, 12))} C{f(P(a + 200, 30))} {f(P(a + 60, 70))} {f(P(a, 60))} Z"
    rim = d.split(" C", 1)[0]  # start point
    rim_d = f"M{f(P(*outer[0]))}" + d.split(f"{f(P(*outer[0]))}", 1)[1]
    inner_edge = f"M{f(P(a, 60))} C{f(P(a + 60, 70))} {f(P(a + 200, 30))} {f(P(b - 200, 12))} C{f(P(b - 120, 8))} {f(P(b + 30, 20))} {f(P(L - 4, 2))}"
    return d + inner, rim_d, inner_edge


def ribs():
    out = []
    u0 = SUTURES[-1]
    for v0, v1, uend in [(-150, -40, u0 + 380), (-110, -20, u0 + 440), (-60, 0, u0 + 480), (-190, -90, u0 + 280)]:
        out.append(f"M{f(P(u0 + 16, v0))} C{f(P(u0 + 120, v0 - 30))} {f(P(uend - 100, v1 - 10))} {f(P(uend, v1))}")
    for i in range(len(SUTURES) - 1):   # short ribs on each spire whorl, running down from the crown
        s0, s1 = SUTURES[i], SUTURES[i + 1]
        w = w_spire(s0)
        if w > 40:
            for t in (-0.45, 0.35):
                out.append(f"M{f(P(s0 + 0.2 * w, t * w))} Q{f(P((s0 + s1) / 2 + 10, t * w * 1.2))} {f(P(s1 + 4, t * w_spire(s1)))}")
    return out


def lip_lines():
    a, b = SUTURES[-1] + 60, L - 220
    return [f"M{f(P(a + k * 60, 80))} C{f(P(a + k * 60 + 30, 160))} {f(P(a + k * 50 + 40, 240))} {f(P(a + k * 45 + 20, 300 - k * 25))}" for k in range(1, 5)]


def shell_svg():
    parts = []
    whorls = []
    for i in range(len(SUTURES) - 1):
        whorls.append(whorl(SUTURES[i], SUTURES[i + 1]))
    bd, bcrown = body()
    ld, lrim, ledge = lip()
    gold = 'stroke="url(#gold)" stroke-linecap="round" stroke-linejoin="round" fill="none"'
    # draw from the apex down: each lower whorl's crown overlaps the base of the one above it
    for i, (d, cr) in enumerate(whorls):
        parts.append(f'<path d="{d}" fill="url(#shell)" stroke="#d6cdbd" stroke-width="3"/>')
        parts.append(f'<path d="{cr}" {gold} stroke-width="{7 + i * 1.6:.1f}"/>')
    parts.append(f'<path d="{bd}" fill="url(#shell)" stroke="#d6cdbd" stroke-width="3"/>')
    parts.append('<g fill="none" stroke="#e2b04a" stroke-width="4.5" stroke-linecap="round" opacity=".7">' + "".join(f'<path d="{r}"/>' for r in ribs()) + "</g>")
    parts.append(f'<path d="{bcrown}" {gold} stroke-width="16"/>')
    parts.append(f'<path d="{ld}" fill="url(#inner)" stroke="#d6cdbd" stroke-width="3"/>')
    parts.append('<g fill="none" stroke="#d9c9a8" stroke-width="4" stroke-linecap="round" opacity=".7">' + "".join(f'<path d="{r}"/>' for r in lip_lines()) + "</g>")
    parts.append(f'<path d="{lrim}" {gold} stroke-width="15"/>')
    parts.append(f'<path d="{ledge}" {gold} stroke-width="18"/>')
    a = P(-26, 0)
    parts.append(f'<path d="M{f(a)} L{f(P(12, -10))} L{f(P(12, 10))} Z" fill="url(#gold)"/>')
    return "\n    ".join(parts)


DEFS = """<defs>
    <radialGradient id="bg" cx="42%" cy="32%" r="85%"><stop offset="0" stop-color="#f39a3a"/><stop offset=".55" stop-color="#d65a20"/><stop offset="1" stop-color="#8f2414"/></radialGradient>
    <linearGradient id="shell" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset=".6" stop-color="#f8f4ec"/><stop offset="1" stop-color="#e6dfd2"/></linearGradient>
    <linearGradient id="inner" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fffdf8"/><stop offset="1" stop-color="#ede4d4"/></linearGradient>
    <linearGradient id="gold" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f8de92"/><stop offset=".5" stop-color="#e0ac46"/><stop offset="1" stop-color="#b5822a"/></linearGradient>
    <filter id="sh" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="16" stdDeviation="18" flood-color="#4a0f06" flood-opacity=".45"/></filter>
  </defs>"""
WAVES = """<g fill="none" stroke="#ffe7b0" stroke-linecap="round" transform="translate(758 768) rotate(40) scale(.8)">
    <path d="M0 -36 q 34 36 0 72" stroke-width="20"/><path d="M42 -72 q 64 72 0 144" stroke-width="16" opacity=".72"/><path d="M84 -108 q 92 108 0 216" stroke-width="12" opacity=".45"/>
  </g>"""


def main():
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">
  <!-- Pāñcajanya, generated by draw_conch.py: white shell, gold crowns on each whorl, flared gold lip. -->
  {DEFS}
  <rect width="1000" height="1000" fill="url(#bg)"/>
  <circle cx="500" cy="500" r="390" fill="none" stroke="#ffd9a0" stroke-opacity=".14" stroke-width="3"/>
  <g transform="translate(500 490) scale(.86) translate(-440 -500)" filter="url(#sh)">
    {shell_svg()}
  </g>
  {WAVES}
</svg>
"""
    open(os.path.join(HERE, "conch_full.svg"), "w").write(svg)
    print("wrote conch_full.svg")


if __name__ == "__main__":
    main()
