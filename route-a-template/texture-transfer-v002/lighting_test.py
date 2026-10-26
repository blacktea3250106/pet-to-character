from pathlib import Path
import bpy
P=Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(P/'semantic-skin-test.blend'))
s=bpy.context.scene
for ob in bpy.data.objects:
    if ob.type=='LIGHT':ob.data.energy*=.22
s.world.node_tree.nodes['Background'].inputs[1].default_value=.18
s.render.resolution_x=1000;s.render.resolution_y=750;s.cycles.samples=16
s.render.filepath=str(P/'preview/lighting-test.png')
bpy.ops.render.render(write_still=True)
