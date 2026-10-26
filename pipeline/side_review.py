"""Render input pose and facial oblique checks; does not modify source scene or cat."""
import ast,math
from pathlib import Path
import bpy
from mathutils import Vector
HERE=Path(__file__).resolve().parent;OUT=HERE/'11-other-side';OUT.mkdir(exist_ok=True)
tree=ast.parse((HERE/'blender_stage.py').read_text())
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'bsdf','make_mat','render'}],type_ignores=[]),'review_helpers','exec'))
bpy.ops.wm.open_mainfile(filepath=str(HERE/'10-style-recovery/eye-material/scene.blend'))
render('opposite-clay',110,10,target=(0,0,.20),scale=.79,clay=True)
render('face-oblique-a',-38,9,target=(.23,0,.31),scale=.28)
render('face-oblique-b',-100,9,target=(.23,0,.31),scale=.28)
render('back-high',110,48,target=(0,0,.20),scale=.79)
