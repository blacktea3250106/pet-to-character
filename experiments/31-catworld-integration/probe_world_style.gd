extends SceneTree
## Read only: inspect imported runtime material properties and REST display bounds.
func _initialize() -> void:
	run.call_deferred()

func material_info(material: Material) -> Dictionary:
	var record := {"class":material.get_class()}
	if material is BaseMaterial3D:
		record.merge({"roughness":material.roughness,"metallic":material.metallic,"specular":material.metallic_specular,"shading_mode":material.shading_mode,"albedo_color":str(material.albedo_color),"vertex_color_albedo":material.vertex_color_use_as_albedo,"vertex_color_srgb":material.vertex_color_is_srgb,"normal_enabled":material.normal_enabled,"ao_enabled":material.ao_enabled,"emission_enabled":material.emission_enabled,"albedo_texture":str(material.albedo_texture.get_size()) if material.albedo_texture else null})
	return record

func run() -> void:
	var scene: Node3D = load("res://main.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	var report := {"camera":{"projection":scene.cam.projection,"size":scene.cam.size,"position":str(scene.cam.global_position),"viewport":str(root.size)},"objects":[],"lights":[],"scope":"Runtime material parameters and REST mesh AABBs; AABBs are not animated surface contact/visibility measurements."}
	for object: Node3D in [scene.room,scene.cat,scene.tripo_cat,scene.personalized_cat]:
		var meshes: Array[Dictionary] = []
		var bounds := AABB()
		var found := false
		for mesh: MeshInstance3D in object.find_children("*","MeshInstance3D",true,false):
			if not mesh.is_visible_in_tree():
				continue
			var box: AABB = mesh.global_transform * mesh.get_aabb()
			bounds = bounds.merge(box) if found else box
			found = true
			var surfaces: Array[Dictionary] = []
			for surface in mesh.mesh.get_surface_count():
				surfaces.append(material_info(mesh.get_active_material(surface)))
			meshes.append({"name":str(mesh.name),"materials":surfaces})
		report.objects.append({"name":str(object.name),"scale":str(object.scale),"rest_world_bounds_size":str(bounds.size),"rest_world_bounds_position":str(bounds.position),"meshes":meshes})
	for light: Light3D in scene.find_children("*","Light3D",true,false):
		report.lights.append({"name":str(light.name),"color":str(light.light_color),"energy":light.light_energy,"shadow":light.shadow_enabled,"shadow_bias":light.shadow_bias,"shadow_normal_bias":light.shadow_normal_bias})
	var environment: Environment = scene.find_children("*","WorldEnvironment",true,false)[0].environment
	report["environment"]={"ambient_color":str(environment.ambient_light_color),"ambient_energy":environment.ambient_light_energy,"tonemap":environment.tonemap_mode,"ssao_enabled":environment.ssao_enabled,"ssil_enabled":environment.ssil_enabled,"sdfgi_enabled":environment.sdfgi_enabled}
	FileAccess.open(get_script().resource_path.get_base_dir()+"/world-style-probe.json",FileAccess.WRITE).store_string(JSON.stringify(report,"  "))
	print("WORLD_STYLE_PROBE_COMPLETE")
	quit()
