"""The road tiles (vk_mod_roads) with the paving tiles (vk_mod_paving): push the texts, rebuild the 17 road pieces, lay
out the review scene RD_Review (a cobbled square, and a road loop round a block that leaves it twice -- north and east,
up to its curb -- with a crossing, T junctions, bends, straights and dead ends, then every road piece in a row), render the review shots to renders/roads/, save the .blend.

    blender.exe -b blender/medievalDiorama.blend --python tools/roads_run.py -- [build] [scene] [shots] [save]
In the open Blender: ARGS = ["build", "scene"]; exec(open(r"...\\tools\\roads_run.py").read())
"""
import bpy, sys, os, time
ROOT = r"E:\Unity\Projects\GameArtGeneration\MedievalVillageKit"
OUT = os.path.join(ROOT, "renders", "roads")
if "ARGS" in globals(): args = list(ARGS)
else: args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["build", "scene", "shots", "save"]
t0 = time.time()
exec(open(os.path.join(ROOT, "tools", "kit_sync.py"), encoding="utf8").read())
print("PUSH", push(["vk_helpers", "vk_kit", "vk_mod_paving", "vk_mod_roads"]))
exec(bpy.data.texts["vk_kit"].as_string())
g = vk_kit_ns()
names = list(g["KIT_MODULE_SPECS"]["vk_mod_roads"])
if "build" in args:
    g["full_rebuild"](names=set(names))
    print("TRIS", {n: sum(len(p.vertices) - 2 for p in bpy.data.objects[n].data.polygons) for n in names})

SC = "RD_Review"
# 3 m cells: the square (5 x 4, its NE cell out, a green inside, a street south, an arm east)
PAVE = ({(i, j) for i in range(5) for j in range(4)} - {(4, 3), (1, 2)}) | {(2, -1), (2, -2), (2, -3), (5, 1), (6, 1)}
# the roads: out of the arm east to a crossing, north to a T, west round a block back into the square from the north;
# from the crossing south to a bend and a dead end, east to a dead end; a stub north of the T
ROADS = {(7, 1), (8, 1), (9, 1), (10, 1), (11, 1), (9, 0), (9, -1), (8, -1), (7, -1), (7, -2), (7, -3),
         (9, 2), (9, 3), (9, 4), (10, 4), (10, 5), (8, 4), (7, 4), (6, 4), (5, 4), (5, 5), (5, 6), (4, 6), (3, 6),
         (2, 6), (2, 5), (2, 4)}
JOINS = {(6, 1), (2, 3)}          # the paving cells the roads run into (up to their curb)
if "scene" in args:
    sc = bpy.data.scenes.get(SC) or bpy.data.scenes.new(SC)
    vk = bpy.data.scenes["VillageKit"]
    for o in list(sc.collection.all_objects):
        if o.name not in ("VK_Sun", "VK_Fill"): bpy.data.objects.remove(o)
    for c in list(sc.collection.children):
        sc.collection.children.unlink(c)
        if c.users == 0: bpy.data.collections.remove(c)
    for n in ("VK_Sun", "VK_Fill"):
        if n not in sc.collection.objects: sc.collection.objects.link(bpy.data.objects[n])
    sc.world = vk.world
    for a in ("view_transform", "look", "exposure", "gamma"): setattr(sc.view_settings, a, getattr(vk.view_settings, a))
    sc.render.engine = vk.render.engine
    coll = bpy.data.collections.new("RD_Roads"); sc.collection.children.link(coll)
    # grass ground (PAV_Review's: the terrain's grass texture from above), its top at z 0
    me = bpy.data.meshes.get("RD_GroundMesh") or bpy.data.meshes.new("RD_GroundMesh")
    me.clear_geometry(); me.from_pydata([(-20, -20, 0), (100, -20, 0), (100, 45, 0), (-20, 45, 0)], [], [(0, 1, 2, 3)])
    me.materials.clear(); me.materials.append(bpy.data.materials["PAV_GroundMat"])
    gp = bpy.data.objects.new("RD_Ground", me); coll.objects.link(gp)
    g["pav_place"](coll, PAVE, worn=0.25, seed=4)
    placed = g["rd_place"](coll, ROADS, joins=JOINS, seed=3)
    # every road piece in a row behind (4 m apart)
    x = -1.5
    for n in names:
        o = bpy.data.objects.new(n + "_rev", bpy.data.objects[n].data); coll.objects.link(o); o.location = (x, 30.0, 0.0)
        x += 4.0
    sc["rd_row"] = [-1.5, x - 4.0, 30.0]
    print("SCENE", len(placed), "road pieces,", len(names), "in the row")

if "shots" in args:
    exec(bpy.data.texts["vk_render"].as_string(), g)
    os.makedirs(OUT, exist_ok=True)
    shot = lambda n, cam, tgt, lens=35, res=(1600, 1000): g["shot"](n, cam, tgt, lens=lens, res=res, scene=SC, outdir=OUT)
    shot("rd_game_cam", (15, -40, 42), (15, 6, 0), lens=30)
    shot("rd_overview_34", (16, -12, 16), (15, 6, 0), lens=30)
    shot("rd_crossing", (27, -2.5, 5.0), (27, 3.0, 0))
    shot("rd_t_north", (27, 8.5, 5.0), (27, 13.0, 0))
    shot("rd_bend_low", (18.5, -12.5, 2.0), (21.5, -4.5, 0.1))
    shot("rd_into_square_north", (6.0, 17.0, 4.2), (6.0, 11.0, 0))
    shot("rd_into_square_east", (25.0, 3.0, 3.6), (19.0, 3.0, 0))
    shot("rd_dead_end", (33.0, -1.5, 4.0), (33.0, 3.0, 0))
    x0, x1, y = bpy.data.scenes[SC]["rd_row"]
    for part, (a, b) in (("row_a", (x0, x0 + 32)), ("row_b", (x0 + 36, x1))):
        xc = (a + b) / 2; d = (b - a) * 0.42 + 3
        shot("rd_" + part, (xc, y - d * 0.6, d), (xc, y, 0), res=(1800, 900))

if "save" in args:
    bpy.ops.wm.save_mainfile()
    print("SAVED")
print("DONE %.0f s" % (time.time() - t0))
