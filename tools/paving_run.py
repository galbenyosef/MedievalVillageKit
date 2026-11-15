"""The paving tiles (vk_mod_paving): push the texts, rebuild the pieces, lay out the review scene PAV_Review (a test
plaza from pav_place with every case -- concave turns, a green inside it, a path, an arm, a lone cell --, a second one
laid with fade=True east of it, and every piece in a row), render the review shots to renders/paving/, save the .blend.

    blender.exe -b blender/medievalDiorama.blend --python tools/paving_run.py -- [build] [scene] [shots] [save]
In the open Blender: ARGS = ["build", "scene"]; exec(open(r"...\\tools\\paving_run.py").read())
"""
import bpy, sys, os, time
ROOT = r"E:\Unity\Projects\GameArtGeneration\MedievalVillageKit"
OUT = os.path.join(ROOT, "renders", "paving")
if "ARGS" in globals(): args = list(ARGS)
else: args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["build", "scene", "shots", "save"]
t0 = time.time()
exec(open(os.path.join(ROOT, "tools", "kit_sync.py"), encoding="utf8").read())
print("PUSH", push(["vk_helpers", "vk_kit", "vk_mod_paving"]))
exec(bpy.data.texts["vk_kit"].as_string())
g = vk_kit_ns()
names = list(g["KIT_MODULE_SPECS"]["vk_mod_paving"])
if "build" in args:
    g["full_rebuild"](names=set(names))
    print("TRIS", {n: sum(len(p.vertices) - 2 for p in bpy.data.objects[n].data.polygons) for n in names})

SC = "PAV_Review"
# the test plaza (3 m cells): 5 x 4 with its NE cell left out, a green inside it, a path south, an arm east, a lone cell
PLAZA = {(i, j) for i in range(5) for j in range(4)} - {(4, 3), (1, 2)}
PLAZA |= {(2, -1), (2, -2), (2, -3), (5, 1), (6, 1), (8, 3)}
# the fade plaza (2026-11-15), 42 m east: a 4 x 3 block with a one-cell notch, an arm two cells off (the gap fills in),
# a path south and a lone cell
FADE = {(i, j) for i in range(4) for j in range(3)} - {(3, 2)}
FADE |= {(5, 1), (1, -1), (1, -2), (7, 4)}
FADE_X = 42.0
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
    coll = bpy.data.collections.new("PAV_Plaza"); sc.collection.children.link(coll)
    # grass ground (the terrain's grass texture from above), its top at z 0
    me = bpy.data.meshes.get("PAV_GroundMesh") or bpy.data.meshes.new("PAV_GroundMesh")
    me.clear_geometry(); me.from_pydata([(-20, -20, 0), (180, -20, 0), (180, 45, 0), (-20, 45, 0)], [], [(0, 1, 2, 3)])
    gm = bpy.data.materials.get("PAV_GroundMat")
    if gm is None:
        gm = bpy.data.materials.new("PAV_GroundMat"); gm.use_nodes = True; nt = gm.node_tree
        b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        tc = nt.nodes.new("ShaderNodeTexCoord"); sv = nt.nodes.new("ShaderNodeVectorMath"); sv.operation = "SCALE"
        sv.inputs["Scale"].default_value = 0.35; im = nt.nodes.new("ShaderNodeTexImage"); im.image = bpy.data.images["T_VK_Grass_BC"]
        nt.links.new(tc.outputs["Object"], sv.inputs[0]); nt.links.new(sv.outputs["Vector"], im.inputs[0])
        nt.links.new(im.outputs[0], b.inputs["Base Color"]); b.inputs["Roughness"].default_value = 0.95
    me.materials.clear(); me.materials.append(gm)
    gp = bpy.data.objects.new("PAV_Ground", me); coll.objects.link(gp)
    placed = g["pav_place"](coll, PLAZA, origin=(0.0, 0.0, 0.0), worn=0.3, seed=4)
    placed += g["pav_place"](coll, FADE, origin=(FADE_X, 0.0, 0.0), worn=0.3, seed=5, fade=True)
    # every piece in a row behind the plaza (4 m apart), the corner stones on a full tile each
    x = -1.5
    for n in names:
        o = bpy.data.objects.new(n + "_rev", bpy.data.objects[n].data); coll.objects.link(o); o.location = (x, 24.0, 0.0)
        if "_Corner_" in n:
            f = bpy.data.objects.new(n + "_revbase", bpy.data.objects["SM_VK_Paving_Full"].data); coll.objects.link(f)
            f.location = (x, 24.0, 0.0)
        x += 4.0
    sc["pav_row"] = [-1.5, x - 4.0, 24.0]
    print("SCENE", len(placed), "plaza pieces,", len(names), "in the row")

if "shots" in args:
    exec(bpy.data.texts["vk_render"].as_string(), g)
    os.makedirs(OUT, exist_ok=True)
    g["shot"]("pav_game_cam", (9, -40, 38), (9, 1, 0), lens=30, res=(1600, 1000), scene=SC, outdir=OUT)
    g["shot"]("pav_plaza_34", (9, -16, 14), (7, 2, 0), lens=30, res=(1600, 1000), scene=SC, outdir=OUT)
    g["shot"]("pav_green_close", (3.0, 0.5, 4.2), (3.0, 5.6, 0), lens=35, res=(1600, 1000), scene=SC, outdir=OUT)
    g["shot"]("pav_notch_close", (10.5, 3.0, 4.0), (11.6, 7.4, 0), lens=35, res=(1600, 1000), scene=SC, outdir=OUT)
    g["shot"]("pav_path_low", (8.0, -11.0, 2.2), (6.0, -4.0, 0.2), lens=35, res=(1600, 1000), scene=SC, outdir=OUT)
    g["shot"]("pav_worn_close", (4.5, 19.0, 4.6), (4.5, 24.0, 0.0), lens=35, res=(1600, 1000), scene=SC, outdir=OUT)
    g["shot"]("pav_fade_game_cam", (FADE_X + 9, -36, 34), (FADE_X + 9, 3, 0), lens=30, res=(1600, 1000), scene=SC, outdir=OUT)
    g["shot"]("pav_fade_34", (FADE_X + 5, -13, 10), (FADE_X + 5, 2.5, 0), lens=30, res=(1600, 1000), scene=SC, outdir=OUT)
    g["shot"]("pav_fade_edge_low", (FADE_X + 13.5, -2.0, 2.0), (FADE_X + 10.0, 4.0, 0.1), lens=35, res=(1600, 1000), scene=SC, outdir=OUT)
    g["shot"]("pav_fade_lone", (FADE_X + 21, 6.5, 8.5), (FADE_X + 21, 12.0, 0.0), lens=35, res=(1600, 1000), scene=SC, outdir=OUT)
    x0, x1, y = bpy.data.scenes[SC]["pav_row"]; step = 44.0; a = x0; i = 0
    while a <= x1:
        b = min(a + step - 4, x1); xc = (a + b) / 2; d = max(b - a, 20) * 0.55 + 4; i += 1
        g["shot"]("pav_row_" + "abcdefgh"[i - 1], (xc, y - d, d * 0.75), (xc, y, 0), lens=35, res=(1800, 900), scene=SC, outdir=OUT)
        a += step

if "save" in args:
    bpy.ops.wm.save_mainfile()
    print("SAVED")
print("DONE %.0f s" % (time.time() - t0))
