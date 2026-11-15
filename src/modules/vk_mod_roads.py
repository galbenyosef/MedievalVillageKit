# ===================== WS_ROADS: dirt road tiles on the 3 m grid =====================
# prefix rd_. 2026-11-15: after the paving tiles (vk_mod_paving) Daniel chose "Road tiles first" for the kit's next
# update: with them a town can be laid out from tiles alone, cobbled squares and streets (paving) and the dirt roads
# between them. Runs after vk_mod_paving (uses PAV_E, PAV_DIR, PAV_SIDES, pav_combos, pav_seed, pav_face's DIRT slot).
# Frame and rule as the paving's: one 3 m cell, origin at its centre on the ground (z 0), N = +Y, E = +X; PLACE THEM
# UNROTATED, one per cell centre (the dirt is mapped in object space, one repeat per tile: UV = x / 3, y / 3).
#   SM_VK_Road_<sides>   the road runs to the middle of each side in <sides> (letters in N E S W order): a dead end
#                        (N, E, S, W: the road comes in from that side and stops), a straight (NS, EW; _B: the same
#                        with another wobble), a bend (NE, NW, ES, SW: a quarter circle about that cell corner), a T
#                        (NES, NEW, NSW, ESW), a crossing (NESW)
# A piece is a heightfield on a regular grid (RD_N x RD_N cells over the tile): the road's surface RD_TOP above the
# ground, its edge sinking to RD_SINK under it, so the line where it meets the ground (the visible edge) follows the
# outline smoothly; the mesh is cut level at RD_CUT under the ground and the rest dropped. Two soft ruts RD_RUT either side of the centreline,
# darker; the verge darker and a little greener. Seams: within RD_PURE of a side the height and colour depend only on
# the road crossing that side (distance to its centreline, the shared wobble rd_pnoise: periodic over the tile), so any
# two tiles meet exactly; the piece's own wobble and mottling, the junctions' rounded corners and a dead end's taper
# fade out before it.
import bpy, bmesh, math, random
from mathutils import Vector, noise as _rnoise

RD_N = 16            # grid cells per tile side (0.1875 m)
RD_W = 1.0           # half-width of the road at its visible edge
RD_TOP = 0.025       # road surface above the ground
RD_SINK = -0.03      # its edge sinks to this under the ground
RD_IN, RD_OUT = 0.16, 0.10   # the edge's slope: full height RD_IN inside the edge, sunk RD_OUT outside it
RD_RUT, RD_RUT_W, RD_RUT_D = 0.5, 0.2, 0.016   # ruts: off the centreline, half-width, depth
RD_FILLET = 0.6      # the rounding of a junction's inner corners (smooth-min radius)
RD_PURE = 0.4        # within this of a side only that side's road counts (the seam rule)
RD_DEAD = 0.3        # a dead end's centreline stops this far past the cell centre
RD_REPEAT = 3.0      # one texture repeat per tile
RD_CUT = -0.02       # the mesh is cut level here, under the ground: the buried edge (ground up to 2 cm low hides it)
_RD_P = [(1, 0, 0.9, 0.3), (0, 1, 0.8, 1.7), (1, 1, 0.6, 2.9), (1, -1, 0.6, 4.1), (2, 1, 0.4, 0.6), (1, 2, 0.4, 5.2),
         (2, -1, 0.35, 3.3), (-1, 2, 0.35, 1.1), (3, 1, 0.25, 2.2), (1, 3, 0.25, 4.7)]


def _ss(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def _smin(a, b, k):
    if k <= 1e-6: return min(a, b)
    h = max(k - abs(a - b), 0.0) / k
    return min(a, b) - h * h * k * 0.25


def _seg_d(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay; L2 = vx * vx + vy * vy
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    return math.hypot(px - ax - t * vx, py - ay - t * vy)


def rd_pnoise(x, y, ph=0.0):
    """smooth noise, about -1..1, periodic over the 3 m tile in x and y (the same on both sides of every seam)"""
    return sum(a * math.sin(2 * math.pi * (i * x + j * y) / CELL + p + ph * (n + 1))
               for n, (i, j, a, p) in enumerate(_RD_P)) / 2.2


def rd_field(sides, seed=0):
    """the road of one tile as a function (x, y) -> (height, (r, g, b) shade)"""
    rnd = random.Random(seed); ox, oy = rnd.uniform(0, 100), rnd.uniform(0, 100)
    D = [PAV_DIR[s] for s in sides]
    bend = len(sides) == 2 and sides not in ("NS", "EW")
    dead = len(sides) == 1
    if bend: cx, cy = PAV_E * (D[0][0] + D[1][0]), PAV_E * (D[0][1] + D[1][1])
    full = [s for s in ("NS", "EW") if s[0] in sides and s[1] in sides]          # straight runs through the cell
    half = [PAV_DIR[s] for s in sides if not any(s in f for f in full)]          # arms from the centre to a side
    own = lambda x, y, z: _rnoise.noise(Vector((x * 0.8 + ox, y * 0.8 + oy, z)))  # the piece's own noise

    def at(x, y):
        m = max(abs(x), abs(y))
        fade = _ss(PAV_E - RD_PURE, PAV_E - RD_PURE - 0.4, m)        # 1 in the middle, 0 near the sides
        s = 9.0; taper = 1.0
        if bend: d = abs(math.hypot(x - cx, y - cy) - PAV_E)
        elif dead:
            dx, dy = D[0]; s = x * dx + y * dy
            d = _seg_d(x, y, PAV_E * dx, PAV_E * dy, -RD_DEAD * dx, -RD_DEAD * dy)
            taper = 0.7 + 0.3 * _ss(-0.4, 0.9, s)
        else:
            ds = [_seg_d(x, y, PAV_E * PAV_DIR[f[1]][0], PAV_E * PAV_DIR[f[1]][1],
                         PAV_E * PAV_DIR[f[0]][0], PAV_E * PAV_DIR[f[0]][1]) for f in full]
            dh = [(_seg_d(x, y, 0.0, 0.0, PAV_E * dx, PAV_E * dy), (dx, dy)) for dx, dy in half]
            kf = RD_FILLET * _ss(PAV_E - RD_PURE, PAV_E - RD_PURE - 0.3, m)
            if ds:
                d = ds[0]
                for e in ds[1:]: d = _smin(d, e, kf)
                for e, (dx, dy) in dh: d = _smin(d, e, kf * _ss(-0.1, 0.4, x * dx + y * dy))   # round the branch's side only
            else:
                d = dh[0][0]
                for e, (dx, dy) in dh[1:]: d = _smin(d, e, kf)
        w = (RD_W + 0.06 * rd_pnoise(x, y) + 0.07 * own(x, y, 1.3) * fade) * taper
        e = w - d
        rut_at = RD_RUT + 0.035 * rd_pnoise(x, y, 1.3) + 0.03 * own(x, y, 4.1) * fade
        rut = (1 - _ss(0.0, 1.0, abs(d - rut_at) / RD_RUT_W)) * _ss(0.05, 0.3, e) * (_ss(-0.3, 0.8, s) if dead else 1.0)
        h = RD_SINK + (RD_TOP - RD_SINK) * _ss(-RD_OUT, RD_IN, e) - RD_RUT_D * rut
        verge = 1 - _ss(-0.05, 0.35, e)
        mot = 1 + 0.07 * rd_pnoise(x, y, 2.1) + 0.05 * own(x, y, 7.7) * fade
        c = (mot * (1 - 0.16 * rut) * (1 - 0.10 * verge), mot * (1 - 0.20 * rut) * (1 - 0.02 * verge),
             mot * (1 - 0.24 * rut) * (1 - 0.18 * verge))
        return h, c
    return at


def rd_road(k, sides, seed=0):
    """one road tile: the field sampled on the grid, each quad split along its flatter diagonal, then cut level at
    RD_CUT and the part below dropped (the buried edge follows the outline instead of the grid's steps, and lies the
    same on both sides of a seam: a cut side edge has the same two ends in both tiles); smooth-shaded dirt, UVs from
    x, y and the field's shade per vertex"""
    k.face_g = {}; k.vert_c = {}; k.smooth_mi = (DIRT,)
    f = rd_field(sides, seed); bm = k.bm; st = CELL / RD_N
    H = {}; V = {}
    for i in range(RD_N + 1):
        for j in range(RD_N + 1):
            H[i, j] = f(-PAV_E + i * st, -PAV_E + j * st)[0]

    def vert(i, j):
        if (i, j) not in V: V[i, j] = bm.verts.new((-PAV_E + i * st, -PAV_E + j * st, H[i, j]))
        return V[i, j]
    for i in range(RD_N):
        for j in range(RD_N):
            q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            if max(H[c] for c in q) <= RD_CUT: continue
            a, b, c, d = (vert(*c) for c in q)                  # counter-clockwise from above
            for t in (((a, b, c), (a, c, d)) if abs(a.co.z - c.co.z) <= abs(b.co.z - d.co.z) else ((a, b, d), (b, c, d))):
                bm.faces.new(t).material_index = DIRT
    geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=(0.0, 0.0, RD_CUT), plane_no=(0.0, 0.0, 1.0), clear_inner=True)
    for fc in bm.faces:
        fc.material_index = DIRT
        for l in fc.loops: l[k.uv].uv = (l.vert.co.x / RD_REPEAT, l.vert.co.y / RD_REPEAT)
    for v in bm.verts: k.vert_c[v] = f(v.co.x, v.co.y)[1]


def rd_pieces_for(cells, joins=(), seed=1):
    """the rule as code: [(piece name, (i, j))] for a set of road cells (cell (i, j) centred at x 3i, y 3j): each tile
    named by the sides whose neighbour is a road cell or one of `joins` (paving cells the road runs into); straights
    alternate between their two wobbles; a road cell with no road beside it gets nothing"""
    S = set(cells); J = set(joins); rnd = random.Random(seed); out = []
    for (i, j) in sorted(S):
        sides = "".join(d for d in PAV_SIDES if (i + PAV_DIR[d][0], j + PAV_DIR[d][1]) in S | J)
        if not sides: continue
        nm = "SM_VK_Road_" + sides
        if sides in ("NS", "EW") and rnd.random() < 0.5: nm += "_B"
        out.append((nm, (i, j)))
    return out


def rd_place(coll, cells, origin=(0.0, 0.0, 0.0), joins=(), seed=1):
    """lay a road network out in Blender: an instance of each master (sharing its mesh) per rd_pieces_for entry"""
    out = []
    for nm, (i, j) in rd_pieces_for(cells, joins, seed):
        o = bpy.data.objects.new(nm + "_inst", bpy.data.objects[nm].data); coll.objects.link(o)
        o.location = (origin[0] + CELL * i, origin[1] + CELL * j, origin[2]); out.append(o)
    return out


# ================================================================ SPECS
_rd_kw = dict(wobble=False, grime=False, nudge=False)
WS_SPECS = [("SM_VK_Road_" + s, (lambda s_: (lambda k: rd_road(k, s_, seed=pav_seed("road" + s_))))(s), _rd_kw)
            for s in pav_combos()]
WS_SPECS += [("SM_VK_Road_" + s + "_B", (lambda s_: (lambda k: rd_road(k, s_, seed=pav_seed("road_b" + s_))))(s), _rd_kw)
             for s in ("NS", "EW")]
EXTRA_SPECS += WS_SPECS
