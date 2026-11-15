# ===================== WS_PAVING: cobbled paving tiles on the 3 m grid =====================
# prefix pav_. 2026-11-14: an itch.io buyer asked where the town centre's "square tiles" are -- the valley's cobbles are
# one generated mesh (vk_terrain.tk_build_paving) -- and Daniel said "Let's do this": the same paving as pieces anyone
# can lay out by hand, in any engine.
# Frame: one 3 m cell, origin at its centre on the ground (z 0), fronts toward -Y as every kit piece (N = +Y, E = +X).
# PLACE THEM UNROTATED, one per cell centre: the cobbles are projected from above in object space, one repeat per tile
# (M_VKT_PavingTile; the top's UVs carry the same mapping for other engines), so neighbours meet seamlessly only in one
# orientation -- hence one piece per curb combination instead of rotated copies.
#   SM_VK_Paving_Full                 paved on every side, no curb; _Full_Worn_A / _B / _C: the same with missing
#                                     stones (dirt below) and sunken ones, the cobble texture's own stones (2026-11-15)
#   SM_VK_Paving_Curb_<sides>         a curb of dressed stones along each side that faces unpaved ground, one tile per
#                                     combination (N, E, S, W, NE ... NESW: the letters always in N E S W order)
#   SM_VK_Paving_Corner_<NE|NW|SE|SW> the corner stone of a concave turn: where a cell's two neighbours are paved and the
#                                     cell between them is not, those two curbs stop short of each other; place it at the
#                                     centre of the paved cell inside the turn (its NE etc. corner gets the stone)
#   SM_VK_Paving_Fade_<corners>       instead of a curb: the paving breaking up into stones and patches and fading out,
#                                     for other terrain to take over (2026-11-15). Named by its paved corners in NE SE SW
#                                     NW order (Fade_NE_SE = paved along the east side); 14 tiles. Where both corners of
#                                     a side are paved the side is whole paving (meets a full tile), where neither is,
#                                     nothing; open below, stones on the ground.
# pav_pieces_for(cells) writes the rule out (fade=True: the fade ring round the cells instead of curbs); pav_place(coll,
# cells, origin) lays a paving out in Blender.
# Cobble top PAV_TOP (6 cm, as the valley's), the slab's bottom PAV_BOT under the ground. A curb's outer face sits PAV_CIN
# inside the cell edge and its stones stop half a joint short of the cell's sides, so no face meets a neighbour's; on a
# curbed side the slab stops under the curb.
import bpy, bmesh, math, random, zlib
from mathutils import Vector, noise as _pnoise

PAV_TOP = 0.06       # cobble surface
PAV_BOT = -0.04      # slab bottom (below the ground)
PAV_HOLE = 0.015     # a missing stone's dirt floor: just above the ground, never in its plane
PAV_CIN = 0.02       # curb outer face inside the cell edge
PAV_CW = 0.2         # curb width
PAV_CH = 0.17        # curb stone height, bottom at PAV_CZ0 (top ~0.12)
PAV_CZ0 = -0.05
PAV_JOINT = 0.03     # gap between curb stones (half of it at a cell's side)
PAV_SLAB_IN = 0.12   # on a curbed side the slab stops this far in (under the curb)
PAV_SIDES = "NESW"
PAV_DIR = {"N": (0, 1), "E": (1, 0), "S": (0, -1), "W": (-1, 0)}
PAV_E = CELL / 2


def pav_seed(name):
    return zlib.crc32(name.encode()) & 0xffff


def pav_combos():
    """every curb combination, in N E S W letter order: N, E, S, W, NE, NS, ... NESW"""
    out = ["".join(c for i, c in enumerate(PAV_SIDES) if m >> i & 1) for m in range(1, 16)]
    return sorted(out, key=lambda s: (len(s), [PAV_SIDES.index(c) for c in s]))


def _pav_uv(co, n):
    """tops: the object-space projection's mapping (one repeat per PAV_REPEAT m); sides: along x 3 m, z"""
    if abs(n[2]) > 0.7: return (co.x / PAV_REPEAT, co.y / PAV_REPEAT)
    if abs(n[0]) > abs(n[1]): return (co.y / PAV_REPEAT, co.z / PAV_REPEAT)
    return (co.x / PAV_REPEAT, co.z / PAV_REPEAT)


def pav_face(k, verts, n, mi, g=1.0):
    """a face on existing BMVerts, wound to face n (Newell normal of the order given), shaded g"""
    P = [v.co for v in verts]; nn = Vector((0.0, 0.0, 0.0))
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        nn += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
    if nn.dot(Vector(n)) < 0: verts = verts[::-1]
    f = k.bm.faces.new(verts); f.material_index = mi
    for l in f.loops: l[k.uv].uv = _pav_uv(l.vert.co, n)
    if g != 1.0: k.face_g[f] = g
    return f


def pav_slab(k, curbs):
    """the cobbled slab: top at PAV_TOP over the cell (stopping under each curb), sides, bottom"""
    x0 = -PAV_E + (PAV_SLAB_IN if "W" in curbs else 0.0); x1 = PAV_E - (PAV_SLAB_IN if "E" in curbs else 0.0)
    y0 = -PAV_E + (PAV_SLAB_IN if "S" in curbs else 0.0); y1 = PAV_E - (PAV_SLAB_IN if "N" in curbs else 0.0)
    V = {}
    for z in (PAV_TOP, PAV_BOT):
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)): V[(x, y, z)] = k.bm.verts.new((x, y, z))
    ring = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    pav_face(k, [V[(x, y, PAV_TOP)] for x, y in ring], (0, 0, 1), PAVE_TILE)
    pav_face(k, [V[(x, y, PAV_BOT)] for x, y in ring], (0, 0, -1), PAVE_TILE)
    for i in range(4):
        (ax, ay), (bx, by) = ring[i], ring[(i + 1) % 4]
        n = (by - ay, ax - bx, 0.0)                  # outward for the counter-clockwise ring
        pav_face(k, [V[(ax, ay, PAV_TOP)], V[(bx, by, PAV_TOP)], V[(bx, by, PAV_BOT)], V[(ax, ay, PAV_BOT)]], n, PAVE_TILE, 0.72)


def pav_stones(rnd, a0, a1):
    """a curb run a0..a1 split into stones 0.42-0.72 m long with PAV_JOINT joints: [(s0, s1)]"""
    spans = []; t = a0
    while a1 - t > 0.85:
        l = rnd.uniform(0.42, 0.72); spans.append((t, t + l)); t += l + PAV_JOINT
    rest = a1 - t
    if rest >= 0.3 or not spans: spans.append((t, a1))
    else:                                            # a stub: the last stone takes it, or the last two share
        s0 = spans[-1][0]; tot = a1 - s0
        if tot <= 0.85: spans[-1] = (s0, a1)
        else:
            h = (tot - PAV_JOINT) / 2; spans[-1] = (s0, s0 + h); spans.append((s0 + h + PAV_JOINT, a1))
    return spans


def pav_curb_run(k, rnd, d, curbs):
    """the curb along side d. N and S runs go the whole way to a curbed end (the corner stone is theirs), E and W runs
    stop a joint short of it; an end without a curb stops half a joint short of the cell's side"""
    along_x = d in "NS"
    lo, hi = ("W", "E") if along_x else ("S", "N")
    def inset(side):
        if side in curbs: return PAV_CIN if along_x else PAV_CIN + PAV_CW + PAV_JOINT
        return PAV_JOINT / 2
    a0, a1 = -PAV_E + inset(lo), PAV_E - inset(hi)
    dx, dy = PAV_DIR[d]; off = PAV_E - PAV_CIN - PAV_CW / 2
    for (s0, s1) in pav_stones(rnd, a0, a1):
        l = s1 - s0; c = (s0 + s1) / 2; h = PAV_CH + rnd.uniform(-0.015, 0.015)
        yaw = math.radians(rnd.uniform(-1.2, 1.2)); roll = math.radians(rnd.uniform(-0.8, 0.8))
        if along_x: cen, size, rot = (c, dy * off, PAV_CZ0 + h / 2), (l, PAV_CW, h), (roll, 0.0, yaw)
        else: cen, size, rot = (dx * off, c, PAV_CZ0 + h / 2), (PAV_CW, l, h), (0.0, roll, yaw)
        k.box(cen, size, CURB, rot=rot, bevel=0.018, jitter=0.003, seed=rnd.randint(0, 99999))


def pav_tile(k, curbs="", seed=0):
    k.face_g = {}
    pav_slab(k, curbs)
    rnd = random.Random(seed)
    for d in curbs: pav_curb_run(k, rnd, d, curbs)


# ---------------------------------------------------------------- the texture's stones (worn and fade tiles)
# 2026-11-15, Daniel: the worn tiles' round holes "do not look very good" -- they cut through the drawn cobbles -- and
# he asked for paving that degrades and fades into nothing, for other terrain to fill in. Both now work on the stones
# of the cobble texture itself: T_VK_Cobble_H segmented into cells (a stone plus its half of the joints around it), so
# a missing stone leaves a stone-shaped hole whose edge runs down the joint, and a fade drops whole stones.
# Outlines: a 0/1 mask per pixel (1 = stone kept) -> integer binomial blur -> marching squares on the pixel corners.
# Integer sums make the field exact, so two tiles compute the same crossings on their shared side to the last bit.
# A cell within PAV_SEAM px of a tile side is decided on that side (its centre moved onto the side), where the fade's
# coverage depends only on the two corners the neighbours share -- so both tiles keep or drop it alike.
PAV_SEG_N = 256       # stone map: 3 m / 256 = 1.2 cm a pixel
PAV_SEG_T = 0.42      # T_VK_Cobble_H above this = stone, below = joint
PAV_SEAM = 10         # px (see above)
PAV_RING = 6          # px of the neighbours' stones the field reads (blur 3 + corner 1 + spare)
PAV_FT = 8191.5       # the field's threshold (half of 4 x 4096; never equal to an integer value)
PAV_SIMP = 0.006      # outline simplification tolerance (m)
PAV_SUNK = 0.02       # worn: a sunken stone's drop
PAV_LOOSE = 0.8       # worn: a loose stone's outline, as a share of the field (shrunk ~2 cm off the hole's edge)
PAV_WORN_EDGE = 14    # worn: changed stones keep this many px off the tile's sides
PAV_FADE_SINK = 0.035 # fade: the stones sink this much where the paving runs out (linear in the coverage)
PAV_FOOT = -0.02      # fade: the walls' foot, under the ground
PAV_FADE_C = ("NE", "SE", "SW", "NW")
_PAV_SEG = {}
_PAV_P = ((3, 1, 1.0, 0.3), (-1, 4, 0.9, 1.7), (4, -3, 0.7, 2.9), (2, 3, 0.8, 4.1), (5, 1, 0.5, 0.8), (-3, -2, 0.6, 5.3))


def pav_pnoise(x, y):
    """clumping noise, about -1..1, periodic over the 3 m tile (features ~0.7 m)"""
    return sum(a * math.sin(2 * math.pi * (i * x + j * y) / CELL + p) for i, j, a, p in _PAV_P) / 2.2


def pav_seg():
    """T_VK_Cobble_H's stones as cells, once per kit namespace. lab (N, N): cell per pixel, rows bottom-up and column 0
    at x -1.5 (u = x / 3 puts the texture's middle on the tile's sides); per cell: cx, cy centre (m), xs / ys within
    PAV_SEAM px of a side, edge (px to the nearest side), nz the fade's per-stone offset, nb neighbour cells"""
    if _PAV_SEG: return _PAV_SEG
    import numpy as np
    im = bpy.data.images["T_VK_Cobble_H"]; w, h = im.size
    buf = np.empty(w * h * 4, np.float32); im.pixels.foreach_get(buf)
    N = PAV_SEG_N; f = h // N
    s = buf.reshape(h, w, 4)[:, :, 0].reshape(N, f, N, f).mean(axis=(1, 3))
    s = np.roll(s, (-N // 2, -N // 2), axis=(0, 1))
    stone = s > PAV_SEG_T; BIG = N * N + 1
    lab = np.where(stone, np.arange(N * N).reshape(N, N), BIG)
    while True:                                      # connected stones (periodic): smallest index wins
        m = lab.copy()
        for ax in (0, 1):
            for sh in (1, -1): m = np.minimum(m, np.roll(lab, sh, axis=ax))
        m = np.where(stone, m, BIG)
        if (m == lab).all(): break
        lab = m
    ids, cnt = np.unique(lab[stone], return_counts=True)
    lab = np.where(np.isin(lab, ids[cnt < 40]), BIG, lab)   # specks: joint
    while (lab == BIG).any():                        # joints to the nearest stone (grown a pixel a step)
        m = lab.copy()
        for ax in (0, 1):
            for sh in (1, -1): m = np.minimum(m, np.roll(lab, sh, axis=ax))
        lab = np.where(lab == BIG, m, lab)
    ids, lab = np.unique(lab, return_inverse=True); lab = lab.reshape(N, N); K = len(ids)
    rr, cc = np.mgrid[0:N, 0:N]; L = lab.ravel()
    def centre(c):                                   # circular mean over the repeat -> m in the tile frame
        a = 2 * np.pi * (c.ravel() + 0.5) / N
        th = np.arctan2(np.bincount(L, np.sin(a), K), np.bincount(L, np.cos(a), K)) % (2 * np.pi)
        return -PAV_E + CELL * th / (2 * np.pi)
    cx, cy = centre(cc), centre(rr)
    near = lambda c: np.bincount(L, ((c < PAV_SEAM) | (c >= N - PAV_SEAM)).ravel(), K) > 0
    edge = np.full(K, N); np.minimum.at(edge, L, np.minimum(np.minimum(cc, N - 1 - cc), np.minimum(rr, N - 1 - rr)).ravel())
    nb = [set() for _ in range(K)]
    for ax in (0, 1):
        o = np.roll(lab, 1, axis=ax); d = lab != o
        for a, b in set(zip(lab[d].tolist(), o[d].tolist())): nb[a].add(b); nb[b].add(a)
    rnd = random.Random(1511)
    nz = [max(-0.42, min(0.42, 0.33 * pav_pnoise(cx[i], cy[i]) + 0.14 * rnd.uniform(-1, 1))) for i in range(K)]
    _PAV_SEG.update(lab=lab, cx=cx, cy=cy, xs=near(cc), ys=near(rr), edge=edge, nz=np.array(nz), nb=nb, K=K)
    return _PAV_SEG


def pav_cov(cs, x, y):
    """the fade's coverage: bilinear between the tile's corners (1 = a paved corner), linear along every side"""
    u = min(max((x + PAV_E) / CELL, 0.0), 1.0); v = min(max((y + PAV_E) / CELL, 0.0), 1.0)
    c = lambda k_: 1.0 if k_ in cs else 0.0
    return c("SW") * (1 - u) * (1 - v) + c("SE") * u * (1 - v) + c("NE") * u * v + c("NW") * (1 - u) * v


def pav_ext():
    """the tile's pixels plus PAV_RING of its neighbours': (cell per pixel, tile offset per column / row, pixel in
    that tile per column / row)"""
    import numpy as np
    seg = pav_seg(); N = PAV_SEG_N; idx = np.arange(-PAV_RING, N + PAV_RING)
    t = np.floor_divide(idx, N); p = np.mod(idx, N)
    return seg["lab"][np.ix_(p, p)], t, p


def pav_fade_mask(cs):
    """1 where a stone is kept: coverage at its centre (on the side for cells near one, see above) + its offset > 0.5"""
    import numpy as np
    seg = pav_seg(); N = PAV_SEG_N; L, t, p = pav_ext()
    side = np.where(p < N // 2, -PAV_E, PAV_E)
    X = np.clip(np.where(seg["xs"][L], (t * CELL + side)[None, :], t[None, :] * CELL + seg["cx"][L]), -PAV_E, PAV_E)
    Y = np.clip(np.where(seg["ys"][L], (t * CELL + side)[:, None], t[:, None] * CELL + seg["cy"][L]), -PAV_E, PAV_E)
    u = (X + PAV_E) / CELL; v = (Y + PAV_E) / CELL
    c = lambda k_: 1.0 if k_ in cs else 0.0
    cov = c("SW") * (1 - u) * (1 - v) + c("SE") * u * (1 - v) + c("NE") * u * v + c("NW") * (1 - u) * v
    return (cov + seg["nz"][L] > 0.5).astype(np.int64)


def pav_field(m):
    """mask (with the ring) -> the field on the pixel corners, (N + 1, N + 1) integers 0..16384, [row j, column i]"""
    k_ = (1, 6, 15, 20, 15, 6, 1); W = m.shape[1] - 6
    a = sum(k_[i] * m[:, i:i + W] for i in range(7)); H = a.shape[0] - 6
    a = sum(k_[i] * a[i:i + H, :] for i in range(7))
    o = PAV_RING - 3; N = PAV_SEG_N; B = a[o - 1:o + N + 1, o - 1:o + N + 1]
    return B[:-1, :-1] + B[1:, :-1] + B[:-1, 1:] + B[1:, 1:]


_PAV_MS = {1: ((0, 3),), 2: ((1, 0),), 3: ((1, 3),), 4: ((2, 1),), 6: ((2, 0),), 7: ((2, 3),), 8: ((3, 2),),
           9: ((0, 2),), 11: ((1, 2),), 12: ((3, 1),), 13: ((0, 1),), 14: ((3, 0),)}


def pav_march(F, T=PAV_FT):
    """marching squares on F at PAV_FT: closed loops of (x, y), the kept side on the left (outer loops counter-
    clockwise). A zero-width ring of outside values round the grid closes the loops along the tile's sides."""
    import numpy as np
    N = F.shape[0] - 1
    P = np.zeros((N + 3, N + 3), np.int64); P[1:-1, 1:-1] = F
    b = (P > T).astype(np.int64)
    case = b[:-1, :-1] | (b[:-1, 1:] << 1) | (b[1:, 1:] << 2) | (b[1:, :-1] << 3)
    X = [-PAV_E + CELL * min(max(g_ - 1, 0), N) / N for g_ in range(N + 3)]
    def pos(e):
        o_, i, j = e; a = int(P[j, i])
        if o_ == 0:
            bb = int(P[j, i + 1]); return (X[i] + (T - a) / (bb - a) * (X[i + 1] - X[i]), X[j])
        bb = int(P[j + 1, i]); return (X[i], X[j] + (T - a) / (bb - a) * (X[j + 1] - X[j]))
    nxt = {}
    for j, i in zip(*np.nonzero((case > 0) & (case < 15))):
        j, i = int(j), int(i); c = int(case[j, i])
        E = ((0, i, j), (1, i + 1, j), (0, i, j + 1), (1, i, j))
        if c in (5, 10):
            mid = int(P[j, i]) + int(P[j, i + 1]) + int(P[j + 1, i + 1]) + int(P[j + 1, i]) > 4 * T
            segs = (((0, 1), (2, 3)) if mid else ((0, 3), (2, 1))) if c == 5 else (((3, 0), (1, 2)) if mid else ((1, 0), (3, 2)))
        else: segs = _PAV_MS[c]
        for a, bb in segs: nxt[E[a]] = E[bb]
    loops = []
    while nxt:
        s, e = nxt.popitem(); lp = [pos(s)]
        while e != s: lp.append(pos(e)); e = nxt.pop(e)
        loops.append(lp)
    return loops


def _pav_area(lp):
    return 0.5 * sum(lp[i - 1][0] * lp[i][1] - lp[i][0] * lp[i - 1][1] for i in range(len(lp)))


def _pav_onb(p):
    return abs(p[0]) == PAV_E or abs(p[1]) == PAV_E


def _pav_dp(P, tol):
    keep = [False] * len(P); keep[0] = keep[-1] = True; st = [(0, len(P) - 1)]
    while st:
        i, j = st.pop()
        if j <= i + 1: continue
        (ax, ay), (bx, by) = P[i], P[j]; dx, dy = bx - ax, by - ay; l = math.hypot(dx, dy); best, bi = -1.0, -1
        for t in range(i + 1, j):
            px, py = P[t]
            d = abs((px - ax) * dy - (py - ay) * dx) / l if l > 1e-12 else math.hypot(px - ax, py - ay)
            if d > best: best, bi = d, t
        if best > tol: keep[bi] = True; st += [(i, bi), (bi, j)]
    return keep


def pav_simplify(lp, tol):
    """drop repeats and the points inside straight runs along the tile's sides (their ends stay: the neighbour has the
    same ones), then Douglas-Peucker between the points left on the sides"""
    pts = []
    for p in lp:
        if not pts or p != pts[-1]: pts.append(p)
    while len(pts) > 1 and pts[0] == pts[-1]: pts.pop()
    n = len(pts)
    if n < 3: return pts
    def run(a, p, b):
        return any(p[ax] == a[ax] == b[ax] and abs(p[ax]) == PAV_E for ax in (0, 1)) and not (abs(p[0]) == abs(p[1]) == PAV_E)
    pts = [pts[i] for i in range(n) if not (_pav_onb(pts[i]) and run(pts[i - 1], pts[i], pts[(i + 1) % n]))]
    n = len(pts); fx = [i for i in range(n) if _pav_onb(pts[i])]
    if not fx: fx = [0, max(range(n), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)]
    out = []
    for a, b in zip(fx, fx[1:] + [fx[0] + n]):
        ch = [pts[i % n] for i in range(a, b + 1)]; kp = _pav_dp(ch, tol)
        out += [ch[i] for i in range(len(ch) - 1) if kp[i]]
    return out


def pav_loops_ok(loops):
    """no two edges of the loops cross or touch (bar neighbours in a loop)"""
    E = []
    for li, lp in enumerate(loops):
        n = len(lp); E += [(li, i, n, lp[i], lp[(i + 1) % n]) for i in range(n)]
    grid = {}; cs = 0.05
    for ei, (_, _, _, a, b) in enumerate(E):
        for gx in range(int(math.floor(min(a[0], b[0]) / cs)), int(math.floor(max(a[0], b[0]) / cs)) + 1):
            for gy in range(int(math.floor(min(a[1], b[1]) / cs)), int(math.floor(max(a[1], b[1]) / cs)) + 1):
                grid.setdefault((gx, gy), []).append(ei)
    def cr(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    seen = set()
    for lst in grid.values():
        for x_ in range(len(lst)):
            for y_ in range(x_ + 1, len(lst)):
                p, q = lst[x_], lst[y_]
                if (p, q) in seen: continue
                seen.add((p, q)); l1, i1, n1, a, b = E[p]; l2, i2, n2, c, d = E[q]
                if l1 == l2 and ((i1 + 1) % n1 == i2 or (i2 + 1) % n2 == i1): continue
                d1, d2, d3, d4 = cr(c, d, a), cr(c, d, b), cr(a, b, c), cr(a, b, d)
                if ((d1 > 0) != (d2 > 0) or d1 == 0 or d2 == 0) and ((d3 > 0) != (d4 > 0) or d3 == 0 or d4 == 0):
                    if max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0])) and \
                       max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1])): return False
    return True


def pav_outline(F, T=PAV_FT):
    """F -> simplified loops (as pav_march), simplified less where the full tolerance would make edges cross"""
    raw = pav_march(F, T)
    for tol in (PAV_SIMP, PAV_SIMP / 3, 0.0):
        loops = [pav_simplify(lp, tol) for lp in raw]
        loops = [lp for lp in loops if len(lp) >= 3 and (any(_pav_onb(p) for p in lp) or abs(_pav_area(lp)) > 2e-5)]
        if pav_loops_ok(loops): return loops
    print("PAV outline: crossing edges left", len(loops))
    return loops


def _pav_edge(bm, a, b):
    return bm.edges.get((a, b)) or bm.edges.new((a, b))


def pav_fill(k, vls, mi, g=1.0):
    """fill loops of BMVerts (even-odd: islands and their holes) facing up; checks the filled area against the loops'"""
    bm = k.bm; z = [[v.co.z for v in vs] for vs in vls]; z0 = vls[0][0].co.z
    for vs in vls:
        for v in vs: v.co.z = z0
    edges = [_pav_edge(bm, vs[i], vs[(i + 1) % len(vs)]) for vs in vls for i in range(len(vs))]
    fs = [f for f in bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)["geom"]
          if isinstance(f, bmesh.types.BMFace)]
    got = 0.0
    for f in fs:
        f.normal_update()
        if f.normal.z < 0: f.normal_flip()
        f.material_index = mi; got += f.calc_area()
        for l in f.loops: l[k.uv].uv = _pav_uv(l.vert.co, (0, 0, 1))
        if g != 1.0: k.face_g[f] = g
    want = abs(sum(_pav_area([(v.co.x, v.co.y) for v in vs]) for vs in vls))
    if abs(got - want) > 1e-4 + 1e-4 * want: print("PAV fill: area %.5f, loops %.5f" % (got, want))
    for vs, zs in zip(vls, z):
        for v, zz in zip(vs, zs): v.co.z = zz
    return fs


def _pav_seam(a, b):
    return (a.x == b.x and abs(a.x) == PAV_E) or (a.y == b.y and abs(a.y) == PAV_E)


def pav_walls(k, vs, zb, mi, g):
    """walls down from a loop to z zb, facing out of the kept side (right of each edge); none along the tile's sides.
    Returns the bottom verts (None where no wall reached)"""
    n = len(vs); bot = [None] * n
    def B(i):
        if bot[i] is None: bot[i] = k.bm.verts.new((vs[i].co.x, vs[i].co.y, zb))
        return bot[i]
    for i in range(n):
        a, b = vs[i], vs[(i + 1) % n]
        if _pav_seam(a.co, b.co): continue
        d = b.co - a.co; pav_face(k, [a, b, B((i + 1) % n), B(i)], (d.y, -d.x, 0.0), mi, g)
    return bot


def pav_pick(lp, lab, d=0.03):
    """the cell just inside a loop (right of its longest edges): a vote over five"""
    N = PAV_SEG_N; votes = {}
    ed = sorted(range(len(lp)), key=lambda i: -math.dist(lp[i], lp[(i + 1) % len(lp)]))[:5]
    for i in ed:
        (ax, ay), (bx, by) = lp[i], lp[(i + 1) % len(lp)]; l = math.hypot(bx - ax, by - ay) or 1.0
        x, y = (ax + bx) / 2 + (by - ay) / l * d, (ay + by) / 2 - (bx - ax) / l * d
        c = int(lab[min(N - 1, max(0, int((y + PAV_E) / CELL * N))), min(N - 1, max(0, int((x + PAV_E) / CELL * N)))])
        votes[c] = votes.get(c, 0) + 1
    return max(votes, key=votes.get)


def pav_worn_cells(seed, holes, sunk):
    """stones to take out (clusters of the sizes in `holes`, each a connected group) and to sink (`sunk` singles), all
    PAV_WORN_EDGE px off the sides and a stone apart from each other; in each cluster of two or more one stone lies
    loose in the hole. Returns (out, sunk, loose)"""
    seg = pav_seg(); rnd = random.Random(seed); nb = seg["nb"]
    ok = [i for i in range(seg["K"]) if seg["edge"][i] >= PAV_WORN_EDGE]; oks = set(ok)
    blocked = set(); H = set(); S = set(); Z = set()
    for size in holes:
        for _ in range(300):
            cl = [rnd.choice(ok)]
            if cl[0] in blocked: continue
            while len(cl) < size:
                cand = sorted({n for c in cl for n in nb[c]} & oks - blocked - set(cl))
                if not cand: break
                cl.append(rnd.choice(cand))
            if len(cl) == size:
                H |= set(cl); blocked |= set(cl) | {n for c in cl for n in nb[c]}
                if size > 1: Z.add(rnd.choice(cl))
                break
    for _ in range(sunk):
        cand = [i for i in ok if i not in blocked]
        if not cand: break
        c = rnd.choice(cand); S.add(c); blocked |= {c} | nb[c]
    return H, S, Z


def pav_worn(k, seed, holes=(2, 1), sunk=3):
    """a full tile with missing stones (`holes`: cluster sizes) down to a dirt floor at PAV_HOLE and sunken ones, the
    texture's own stones (pav_seg): the top square (its sides plain, as the full tile's) around stone-shaped openings"""
    import numpy as np
    k.face_g = {}; bm = k.bm; seg = pav_seg()
    H, S, Z = pav_worn_cells(seed, holes, sunk)
    L, t, p = pav_ext()
    inner = (t[:, None] == 0) & (t[None, :] == 0)
    m = (~(np.isin(L, list(H | S)) & inner)).astype(np.int64)
    loops = pav_outline(pav_field(m))
    vls = [[bm.verts.new((x, y, PAV_TOP)) for x, y in lp] for lp in loops]
    pav_fill(k, vls, PAVE_TILE)
    for lp, vs in zip(loops, vls):
        if _pav_area(lp) > 0:                        # the outer square: plain sides and a bottom, as the full tile
            cor = [v for v in vs if abs(v.co.x) == PAV_E and abs(v.co.y) == PAV_E]
            cor.sort(key=lambda v: math.atan2(v.co.y, v.co.x))
            bot = [bm.verts.new((v.co.x, v.co.y, PAV_BOT)) for v in cor]
            pav_face(k, bot, (0, 0, -1), PAVE_TILE)
            for i in range(4):
                a, b = cor[i], cor[(i + 1) % 4]
                pav_face(k, [a, b, bot[(i + 1) % 4], bot[i]], (b.co.y - a.co.y, a.co.x - b.co.x, 0.0), PAVE_TILE, 0.72)
            continue
        hole = pav_pick(lp, seg["lab"]) in H
        bot = pav_walls(k, vs, PAV_HOLE if hole else PAV_TOP - PAV_SUNK, CURB, 0.5 if hole else 0.42)
        if hole: pav_fill(k, [bot[::-1]], DIRT, 0.62)
        else: pav_fill(k, [bot[::-1]], PAVE_TILE, 0.9)
    rnd = random.Random(seed * 7 + 1)
    for c in sorted(Z):                              # a loose stone: its outline shrunk, tilted, resting on the floor
        mz = ((L == c) & inner).astype(np.int64)
        for lp in pav_outline(pav_field(mz), PAV_LOOSE * 16384 + 0.5):
            if _pav_area(lp) <= 0: continue
            cx = sum(p[0] for p in lp) / len(lp); cy = sum(p[1] for p in lp) / len(lp)
            a = rnd.uniform(0, 2 * math.pi); sl = math.tan(math.radians(rnd.uniform(9, 14)))
            zc = rnd.uniform(0.026, 0.032)
            top = [bm.verts.new((x, y, PAV_TOP)) for x, y in lp]
            pav_fill(k, [top], PAVE_TILE, 0.92)
            for v in top:
                v.co.z = min(PAV_TOP - 0.008, max(PAV_HOLE + 0.008, zc + sl * ((v.co.x - cx) * math.cos(a) + (v.co.y - cy) * math.sin(a))))
            pav_walls(k, top, PAV_HOLE - 0.006, CURB, 0.7)


def pav_fade_sets():
    """the 14 fade tiles' paved-corner sets (none and all four are no tile and the full tile), corners in NE SE SW NW
    order"""
    out = [tuple(c for i, c in enumerate(PAV_FADE_C) if m >> i & 1) for m in range(1, 15)]
    return sorted(out, key=lambda s: (len(s), [PAV_FADE_C.index(c) for c in s]))


def pav_fade(k, cs):
    """a fade tile: the paving of the corners in `cs` breaking up into stones and patches toward the others, nothing
    at all along a side whose corners are both unpaved. Stone tops sink with the coverage (linear along the sides, so
    neighbours meet), a little darker; walls down to PAV_FOOT; open below and wherever the stones are gone"""
    k.face_g = {}; k.vert_c = {}; bm = k.bm
    loops = pav_outline(pav_field(pav_fade_mask(cs)))
    vls = [[bm.verts.new((x, y, 0.0)) for x, y in lp] for lp in loops]
    if not vls: return
    pav_fill(k, vls, PAVE_TILE)
    for vs in vls:
        for v in vs:
            c = pav_cov(cs, v.co.x, v.co.y); v.co.z = PAV_TOP - PAV_FADE_SINK * (1 - c)
            k.vert_c[v] = (0.84 + 0.16 * c, 0.82 + 0.18 * c, 0.8 + 0.2 * c)
    for vs in vls: pav_walls(k, vs, PAV_FOOT, CURB, 0.75)


def pav_corner(k, c="NE", seed=0):
    """the corner stone of a concave turn, in corner c of the cell (origin at the cell's centre like the tiles)"""
    k.face_g = {}
    sx = 1 if "E" in c else -1; sy = 1 if "N" in c else -1
    m = PAV_E - PAV_CIN - PAV_CW / 2; h = PAV_CH + 0.005
    k.box((sx * m, sy * m, PAV_CZ0 + h / 2), (PAV_CW, PAV_CW, h), CURB, bevel=0.018, jitter=0.002, seed=seed)


def pav_pieces_for(cells, worn=0.25, seed=1, fade=False):
    """the rule as code: [(piece name, (i, j))] for a set of paved 3 m cells (cell (i, j) centred at x 3i, y 3j): each
    tile named by its unpaved sides, a share `worn` of the uncurbed ones worn, a corner stone in every concave turn.
    fade=True: no curbs -- the cells are all full tiles and the ring of cells round them (diagonals too) gets the fade
    tiles: a corner is paved when any of the four cells round it is, a cell takes the tile of its paved corners (all
    four: a full tile, so a one-cell gap or notch fills in).
    A road (vk_mod_roads) runs up to the curb: an uncurbed side next to a 2 m road leaves the slab's edge bare"""
    S = set(cells); rnd = random.Random(seed); out = []
    def full():
        r = rnd.random()
        return "SM_VK_Paving_Full" + ("" if r >= worn else "_Worn_" + "ABC"[min(2, int(3 * r / worn))])
    if fade:
        paved = lambda a, b: any((a - di, b - dj) in S for di in (0, 1) for dj in (0, 1))   # vertex (a, b): SW of cell (a, b)
        ring = {(i + di, j + dj) for (i, j) in S for di in (-1, 0, 1) for dj in (-1, 0, 1)}
        for (i, j) in sorted(ring):
            cs = [c for c, (a, b) in zip(PAV_FADE_C, ((i + 1, j + 1), (i + 1, j), (i, j), (i, j + 1))) if paved(a, b)]
            if len(cs) == 4: out.append((full(), (i, j)))
            elif cs: out.append(("SM_VK_Paving_Fade_" + "_".join(cs), (i, j)))
        return out
    for (i, j) in sorted(S):
        sides = "".join(d for d in PAV_SIDES if (i + PAV_DIR[d][0], j + PAV_DIR[d][1]) not in S)
        out.append(("SM_VK_Paving_Curb_" + sides if sides else full(), (i, j)))
        for c in ("NE", "NW", "SE", "SW"):
            a, b = PAV_DIR[c[0]], PAV_DIR[c[1]]
            if (i + a[0], j + a[1]) in S and (i + b[0], j + b[1]) in S and (i + a[0] + b[0], j + a[1] + b[1]) not in S:
                out.append(("SM_VK_Paving_Corner_" + c, (i, j)))
    return out


def pav_place(coll, cells, origin=(0.0, 0.0, 0.0), worn=0.25, seed=1, fade=False):
    """lay a paving out in Blender: an instance of each master (sharing its mesh) per pav_pieces_for entry"""
    out = []
    for nm, (i, j) in pav_pieces_for(cells, worn, seed, fade):
        o = bpy.data.objects.new(nm + "_inst", bpy.data.objects[nm].data); coll.objects.link(o)
        o.location = (origin[0] + CELL * i, origin[1] + CELL * j, origin[2]); out.append(o)
    return out


# ================================================================ SPECS
_pav_kw = dict(wobble=False, grime=False)
_pav_skw = dict(wobble=False, grime=False, nudge=False)     # the stone-outline tiles: one surface, nothing to nudge
WS_SPECS = [("SM_VK_Paving_Full", lambda k: pav_tile(k, ""), _pav_kw),
            ("SM_VK_Paving_Full_Worn_A", lambda k: pav_worn(k, 11, (3, 1), 3), _pav_skw),
            ("SM_VK_Paving_Full_Worn_B", lambda k: pav_worn(k, 23, (5, 2), 2), _pav_skw),
            ("SM_VK_Paving_Full_Worn_C", lambda k: pav_worn(k, 37, (1, 1, 1), 5), _pav_skw)]
WS_SPECS += [("SM_VK_Paving_Curb_" + s, (lambda s_: (lambda k: pav_tile(k, s_, seed=pav_seed(s_))))(s), _pav_kw)
             for s in pav_combos()]
WS_SPECS += [("SM_VK_Paving_Corner_" + c, (lambda c_: (lambda k: pav_corner(k, c_, pav_seed(c_))))(c), _pav_kw)
             for c in ("NE", "NW", "SE", "SW")]
WS_SPECS += [("SM_VK_Paving_Fade_" + "_".join(cs), (lambda cs_: (lambda k: pav_fade(k, cs_)))(cs), _pav_skw)
             for cs in pav_fade_sets()]
EXTRA_SPECS += WS_SPECS
