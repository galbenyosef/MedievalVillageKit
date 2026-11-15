# ===================== WS_PAVING: cobbled paving tiles on the 3 m grid =====================
# prefix pav_. 2026-11-14: an itch.io buyer asked where the town centre's "square tiles" are -- the valley's cobbles are
# one generated mesh (vk_terrain.tk_build_paving) -- and Daniel said "Let's do this": the same paving as pieces anyone
# can lay out by hand, in any engine.
# Frame: one 3 m cell, origin at its centre on the ground (z 0), fronts toward -Y as every kit piece (N = +Y, E = +X).
# PLACE THEM UNROTATED, one per cell centre: the cobbles are projected from above in object space, one repeat per tile
# (M_VKT_PavingTile; the top's UVs carry the same mapping for other engines), so neighbours meet seamlessly only in one
# orientation -- hence one piece per curb combination instead of rotated copies.
#   SM_VK_Paving_Full                 paved on every side, no curb; _Full_Worn_A / _B: the same with missing stones
#   SM_VK_Paving_Curb_<sides>         a curb of dressed stones along each side that faces unpaved ground, one tile per
#                                     combination (N, E, S, W, NE ... NESW: the letters always in N E S W order)
#   SM_VK_Paving_Corner_<NE|NW|SE|SW> the corner stone of a concave turn: where a cell's two neighbours are paved and the
#                                     cell between them is not, those two curbs stop short of each other; place it at the
#                                     centre of the paved cell inside the turn (its NE etc. corner gets the stone)
# pav_pieces_for(cells) writes the rule out; pav_place(coll, cells, origin) lays a paving out in Blender.
# Cobble top PAV_TOP (6 cm, as the valley's), the slab's bottom PAV_BOT under the ground. A curb's outer face sits PAV_CIN
# inside the cell edge and its stones stop half a joint short of the cell's sides, so no face meets a neighbour's; on a
# curbed side the slab stops under the curb. Missing stones: holes in the top down to a dirt floor just above the ground,
# kept PAV_MARGIN off the tile's sides (tiles meet on whole cobbles).
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
PAV_MARGIN = 0.3     # missing stones stay this far off the tile's sides
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


def pav_worn(k, seed, radii):
    """a full tile with missing stones: a roundish patch per radius in `radii` (a lobed, noisy outline, the lobes about
    a cobble across) cut out of the cobble top and opening to a dirt floor at PAV_HOLE, kept PAV_MARGIN off the
    sides; the top is filled around the holes (bmesh triangle_fill), sides and bottom close it"""
    k.face_g = {}
    bm = k.bm; rnd = random.Random(seed)
    ox, oy = rnd.uniform(0, 100), rnd.uniform(0, 100)
    ext = lambda r: r * 1.32 + 0.05                  # a patch's furthest reach from its centre (the outline below)
    ctrs = []
    for r in radii:                                  # centres: inside the margin, the patches apart (else no patch:
        lim = PAV_E - PAV_MARGIN - ext(r)            # outlines that touch make triangle_fill overlap)
        for _ in range(400):
            c = (rnd.uniform(-lim, lim), rnd.uniform(-lim, lim))
            if all(math.hypot(c[0] - q[0], c[1] - q[1]) > ext(r) + ext(rq) + 0.15 for q, rq in ctrs):
                ctrs.append((c, r)); break
    loops = []
    for (c, r) in ctrs:                              # counter-clockwise outlines
        nv = max(10, int(2 * math.pi * r / 0.075)); lobes = max(3, round(2 * math.pi * r / 0.2))
        ph = rnd.uniform(0, 2 * math.pi); pts = []
        for i in range(nv):
            t = 2 * math.pi * i / nv
            rr = r * (1 + 0.3 * _pnoise.noise(Vector((math.cos(t) * 1.3 + ox + c[0], math.sin(t) * 1.3 + oy + c[1], 2.7))))
            rr += 0.022 * math.sin(lobes * t + ph) + rnd.uniform(-0.02, 0.02)
            pts.append((c[0] + rr * math.cos(t), c[1] + rr * math.sin(t)))
        loops.append(pts)
    corners = ((-PAV_E, -PAV_E), (PAV_E, -PAV_E), (PAV_E, PAV_E), (-PAV_E, PAV_E))
    outer = [bm.verts.new((x, y, PAV_TOP)) for x, y in corners]
    edges = [bm.edges.new((outer[i], outer[(i + 1) % 4])) for i in range(4)]
    tops = []
    for pts in loops:
        vs = [bm.verts.new((x, y, PAV_TOP)) for x, y in pts]; tops.append(vs)
        edges += [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
    res = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
    for f in [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace)]:
        f.normal_update()
        if f.normal.z < 0: f.normal_flip()
        f.material_index = PAVE_TILE
        for l in f.loops: l[k.uv].uv = _pav_uv(l.vert.co, (0, 0, 1))
    for vs in tops:
        fl = [bm.verts.new((v.co.x, v.co.y, PAV_HOLE)) for v in vs]
        pav_face(k, fl, (0, 0, 1), DIRT, 0.62)
        for i in range(len(vs)):                     # the hole's sides, facing into it (left of a ccw edge)
            a, b = vs[i], vs[(i + 1) % len(vs)]
            nrm = (-(b.co.y - a.co.y), b.co.x - a.co.x, 0.0)
            pav_face(k, [a, b, fl[(i + 1) % len(vs)], fl[i]], nrm, PAVE_TILE, 0.5)
    bot = [bm.verts.new((x, y, PAV_BOT)) for x, y in corners]
    pav_face(k, bot, (0, 0, -1), PAVE_TILE)
    for i in range(4):
        (ax, ay), (bx, by) = corners[i], corners[(i + 1) % 4]
        pav_face(k, [outer[i], outer[(i + 1) % 4], bot[(i + 1) % 4], bot[i]], (by - ay, ax - bx, 0.0), PAVE_TILE, 0.72)


def pav_corner(k, c="NE", seed=0):
    """the corner stone of a concave turn, in corner c of the cell (origin at the cell's centre like the tiles)"""
    k.face_g = {}
    sx = 1 if "E" in c else -1; sy = 1 if "N" in c else -1
    m = PAV_E - PAV_CIN - PAV_CW / 2; h = PAV_CH + 0.005
    k.box((sx * m, sy * m, PAV_CZ0 + h / 2), (PAV_CW, PAV_CW, h), CURB, bevel=0.018, jitter=0.002, seed=seed)


def pav_pieces_for(cells, worn=0.25, seed=1):
    """the rule as code: [(piece name, (i, j))] for a set of paved 3 m cells (cell (i, j) centred at x 3i, y 3j): each
    tile named by its unpaved sides, a share `worn` of the uncurbed ones worn, a corner stone in every concave turn.
    A road (vk_mod_roads) runs up to the curb: an uncurbed side next to a 2 m road leaves the slab's edge bare"""
    S = set(cells); rnd = random.Random(seed); out = []
    for (i, j) in sorted(S):
        sides = "".join(d for d in PAV_SIDES if (i + PAV_DIR[d][0], j + PAV_DIR[d][1]) not in S)
        if sides: nm = "SM_VK_Paving_Curb_" + sides
        else:
            r = rnd.random(); nm = "SM_VK_Paving_Full" + ("_Worn_A" if r < worn / 2 else "_Worn_B" if r < worn else "")
        out.append((nm, (i, j)))
        for c in ("NE", "NW", "SE", "SW"):
            a, b = PAV_DIR[c[0]], PAV_DIR[c[1]]
            if (i + a[0], j + a[1]) in S and (i + b[0], j + b[1]) in S and (i + a[0] + b[0], j + a[1] + b[1]) not in S:
                out.append(("SM_VK_Paving_Corner_" + c, (i, j)))
    return out


def pav_place(coll, cells, origin=(0.0, 0.0, 0.0), worn=0.25, seed=1):
    """lay a paving out in Blender: an instance of each master (sharing its mesh) per pav_pieces_for entry"""
    out = []
    for nm, (i, j) in pav_pieces_for(cells, worn, seed):
        o = bpy.data.objects.new(nm + "_inst", bpy.data.objects[nm].data); coll.objects.link(o)
        o.location = (origin[0] + CELL * i, origin[1] + CELL * j, origin[2]); out.append(o)
    return out


# ================================================================ SPECS
_pav_kw = dict(wobble=False, grime=False)
WS_SPECS = [("SM_VK_Paving_Full", lambda k: pav_tile(k, ""), _pav_kw),
            ("SM_VK_Paving_Full_Worn_A", lambda k: pav_worn(k, 11, (0.42, 0.3)), _pav_kw),
            ("SM_VK_Paving_Full_Worn_B", lambda k: pav_worn(k, 23, (0.5, 0.32, 0.26)), _pav_kw)]
WS_SPECS += [("SM_VK_Paving_Curb_" + s, (lambda s_: (lambda k: pav_tile(k, s_, seed=pav_seed(s_))))(s), _pav_kw)
             for s in pav_combos()]
WS_SPECS += [("SM_VK_Paving_Corner_" + c, (lambda c_: (lambda k: pav_corner(k, c_, pav_seed(c_))))(c), _pav_kw)
             for c in ("NE", "NW", "SE", "SW")]
EXTRA_SPECS += WS_SPECS
