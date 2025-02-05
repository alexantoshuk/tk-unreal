import unreal
import os

SHOT_SEQUENCE_START = 1001


def find_track(sequence, track_name):
    for track in sequence.get_tracks():
        if track.get_display_name() == track_name:
            return track
    return None


def find_possessable(sequence, actor_name):
    for track in sequence.get_possessables():
        if track.get_display_name() == actor_name:
            return track
    return None


def find_actor(actor_name, actor_class=unreal.GeometryCacheActor):
    # Check if an actor with the same name already exists in the level
    world = unreal.UnrealEditorSubsystem().get_editor_world()
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, actor_class):
        if actor.get_actor_label() == actor_name:
            return actor
    return None


def find_actor_sequence_binding(seq, actor_name):
    def walk(seq):
        for b in seq.get_bindings():
            # unreal.log(f"NAME: {b.get_name()}  {actor_name}")
            if b.get_name() == actor_name:
                return (seq, b)

        for track in seq.get_tracks():
            for section in track.get_sections():
                try:
                    res = walk(section.get_sequence())
                    if res:
                        return res
                except:
                    pass
    return walk(seq)


def get_version(name):
    name, ok, ver = name.rpartition(' v')
    if not ok:
        return 0
    try:
        return int(ver)
    except:
        return None


def set_version(name, ver):
    _name, ok, _ = name.rpartition(' v')
    if ok:
        return f"{_name} v{int(ver)}"
    return f"{name} v{int(ver)}"


def up_version(name):
    _name, ok, ver = name.rpartition(' v')
    if not ok:
        ver = 0
    else:
        ver = int(ver)
        name = _name

    ver += 1
    return f"{name} v{ver}"


def ctx_from_asset_path(path):
    # /Game/Assets/Prop/SM_Gun/SM_Gun
    splitted = path.split('/')
    if splitted[:3] == ['', 'Game', 'Assets']:
        if len(splitted) >= 6:
            asset_type, code, step = splitted[3:6]
        elif len(splitted) == 5:
            asset_type, code = splitted[3:5]
            step = 'MDL'

        return asset_type, code, step

    return None


def ctx_from_shot_path(path):
    splitted = path.split('/')
    if splitted[:3] == ['', 'Game', 'Scenes']:
        if len(splitted) >= 6:
            scn, shot, step = splitted[3:6]
            return scn, shot, step

    return None


def ctx_from_actor_sequence(seq):
    seq_name = seq.get_name()
    seq_name = seq_name.rstrip('_sub')
    l = seq_name.split('_')
    if len(l) != 3:
        return None
    scene, code, step = l
    code = '_'.join((scene, code))
    return scene, code, step


def ctx_from_actor_level(level):
    path = level.get_path_name()
    try:
        scene, code, step = path.split('/')[3:6]
        return scene, code, step
    except:
        return None


def create_asset_context(parent_context, asset_type, code, step):
    import sgtk
    engine = sgtk.platform.current_engine()
    engine.sgtk.synchronize_filesystem_structure()

    root = engine.context.filesystem_locations[0]
    path = os.path.join(root, "assets", asset_type, code, step)

    context = engine.sgtk.context_from_path(path)
    d = context.to_dict()

    task_data = engine.shotgun.find_one("Task", [
        ["step", "is", d["step"]],
        ["entity", "is", d["entity"]],
    ], ["name", "content"])

    if not task_data:
        unreal.log_error(f"Can't find task with step '{step}' for asset '{code}'")

    content = task_data.get('content')
    task_data.setdefault('name', content)

    d['task'] = task_data
    d['source_entity'] = parent_context.source_entity
    context = sgtk.Context.from_dict(engine.sgtk, d)
    return context


def create_shot_context(parent_context, scene, shot, step):
    import sgtk
    engine = sgtk.platform.current_engine()
    engine.sgtk.synchronize_filesystem_structure()

    root = engine.context.filesystem_locations[0]
    path = os.path.join(root, "scenes", scene, shot, step)
    context = engine.sgtk.context_from_path(path)
    d = context.to_dict()
    task_data = engine.shotgun.find_one("Task", [
        ["step", "is", d["step"]],
        ["entity", "is", d["entity"]],
    ], ["name", "content"])

    if not task_data:
        unreal.log_error(f"Can't find task with step '{step}' for shot '{shot}'")

    content = task_data.get('content')
    task_data.setdefault('name', content)

    d['task'] = task_data
    d['source_entity'] = parent_context.source_entity
    context = sgtk.Context.from_dict(engine.sgtk, d)
    return context


def step_short_name(task_id):
    import sgtk
    engine = sgtk.platform.current_engine()
    step = engine.shotgun.find_one("Task", [
        ["id", "is", task_id],

    ], ["step"])['step']

    step_short_name = engine.shotgun.find_one("Step", [["id", "is", step['id']]], ["short_name"])["short_name"]
    return step_short_name


def unreal_import_alembic_asset(input_path, destination_path, destination_name, automated=True, create_actor=False):
    """
    Import an ABC into Unreal Content Browser

    :param input_path: The alembic file to import
    :param destination_path: The Content Browser path where the asset will be placed
    :param destination_name: The asset name to use; if None, will use the filename without extension
    """
    tasks = []
    tasks.append(_generate_alembic_import_task(input_path, destination_path, destination_name, automated=automated))

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

    task = tasks[0]

    if not task.imported_object_paths:
        unreal.log_warning("No objects were imported")
        return None

    unreal.log("Import Task for: {}".format(task.filename))
    geometry_cache_path = task.imported_object_paths[0]
    unreal.log("Imported object: {}".format(geometry_cache_path))

    if create_actor:
        scn, shot, step = ctx_from_shot_path(destination_path)
        level_name = f"{shot}_{step}"
        seq_name = f"{shot}_{step}_sub"

        seq = unreal.load_asset(f"{destination_path}/{seq_name}")

        if seq and find_possessable(seq, destination_name):
            unreal.log(f"Geometry Cache track '{destination_name}' exists. Skip creation.")
            return geometry_cache_path

        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(f"{destination_path}/{level_name}")
        unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(seq)

        actor = find_actor(destination_name, unreal.GeometryCacheActor)
        if actor:
            unreal.log(f"Geometry Cache actor '{destination_name}' exists. Replace it.")
            actor.destroy_actor()
            # return geometry_cache_path

        geometry_cache = unreal.load_asset(geometry_cache_path)

        # Spawn the Geometry Cache actor
        geometry_cache_actor = unreal.EditorActorSubsystem().spawn_actor_from_object(geometry_cache, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        geometry_cache_actor.set_actor_label(destination_name)

        # Add the Geometry Cache actor to the Level Sequence
        possessable = seq.add_possessable(geometry_cache_actor)
        # possessable = seq.add_spawnable_from_instance(geometry_cache_actor)
        track = possessable.add_track(unreal.MovieSceneGeometryCacheTrack)
        section = track.add_section()
        sequence_end = seq.get_playback_end()
        section.set_range(SHOT_SEQUENCE_START, sequence_end)
        section.set_completion_mode(unreal.MovieSceneCompletionMode.KEEP_STATE)
        section.params = unreal.MovieSceneGeometryCacheParams(
            geometry_cache_asset=geometry_cache,
        )
        # Log success
        unreal.log(f"Geometry Cache actor '{destination_name}' added to the level and sequence '{seq_name}'.")
        return geometry_cache_path

    # Focus the Unreal Content Browser on the imported asset
    # unreal.EditorAssetLibrary.sync_browser_to_objects([geometry_cache_path])
    return geometry_cache_path


def unreal_import_alembic_camera(input_path, destination_path, destination_name):
    """
    UNIMPLEMENTED!!!
    """
    tasks = []
    tasks.append(_generate_alembic_camera_import_task(input_path, destination_path, destination_name))

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

    first_imported_object = None

    for task in tasks:
        unreal.log("Import Task for: {}".format(task.filename))
        for object_path in task.imported_object_paths:
            unreal.log("Imported object: {}".format(object_path))
            if not first_imported_object:
                first_imported_object = object_path

    return first_imported_object


def unreal_import_fbx_camera(input_path, destination_path, destination_name):
    """
    Import FBX Camera actor with animation track.

    :param input_path: The fbx file to import
    :param destination_path: The Content Browser path where the asset will be placed
    :param destination_name: The asset name to use; if None, will use the filename without extension
    """

    scn, shot, step = ctx_from_shot_path(destination_path)
    level_name = f"{shot}_{step}"
    seq_name = f"{shot}_{step}_sub"
    cam_name = f"{shot}_Camera"

    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(f"{destination_path}/{level_name}")
    seq = unreal.load_asset(f"{destination_path}/{seq_name}")

    seq, binding = find_actor_sequence_binding(seq, cam_name)

    import_setting = unreal.MovieSceneUserImportFBXSettings()
    import_setting.set_editor_property('create_cameras', False)
    import_setting.set_editor_property('force_front_x_axis', False)
    import_setting.set_editor_property('match_by_name_only', False)
    import_setting.set_editor_property('reduce_keys', True)
    import_setting.set_editor_property('replace_transform_track', True)
    import_setting.set_editor_property('reduce_keys_tolerance', 0.001)

    # world = unreal.EditorLevelLibrary.get_editor_world()
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    ok = unreal.SequencerTools.import_level_sequence_fbx(world, seq, [binding], import_setting, input_path)
    unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(seq)
    return ok


def unreal_import_fbx_asset(input_path, destination_path, destination_name, automated=True):
    """
    Import an FBX into Unreal Content Browser

    :param input_path: The fbx file to import
    :param destination_path: The Content Browser path where the asset will be placed
    :param destination_name: The asset name to use; if None, will use the filename without extension
    """

    tasks = []
    tasks.append(_generate_fbx_import_task(input_path, destination_path, destination_name, automated=automated))

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

    first_imported_object = None

    task = tasks[0]

    if not task.imported_object_paths:
        unreal.log_warning("No objects were imported")
        return None

    unreal.log("Import Task for: {}".format(task.filename))
    object_path = task.imported_object_paths[0]
    unreal.log("Imported object: {}".format(object_path))

    # Focus the Unreal Content Browser on the imported asset
    # unreal.EditorAssetLibrary.sync_browser_to_objects([object_path])
    return object_path


def _generate_fbx_import_task(
    filename,
    destination_path,
    destination_name=None,
    replace_existing=True,
    automated=True,
    save=True,
    materials=True,
    textures=True,
    as_skeletal=False
):
    """
    Create and configure an Unreal AssetImportTask

    :param filename: The fbx file to import
    :param destination_path: The Content Browser path where the asset will be placed
    :return the configured AssetImportTask
    """
    task = unreal.AssetImportTask()
    task.filename = filename
    task.destination_path = destination_path

    # By default, destination_name is the filename without the extension
    if destination_name is not None:
        task.destination_name = destination_name

    task.replace_existing = replace_existing
    task.automated = automated
    task.save = save

    task.options = unreal.FbxImportUI()
    task.options.import_materials = materials
    task.options.import_textures = textures
    task.options.import_as_skeletal = as_skeletal
    # task.options.static_mesh_import_data.combine_meshes = True

    task.options.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    if as_skeletal:
        task.options.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH

    return task


def _generate_alembic_import_task(
    filename,
    destination_path,
    destination_name=None,
    replace_existing=True,
    automated=True,
    save=True,
):
    """
    Create and configure an Unreal AssetImportTask

    :param filename: The fbx file to import
    :param destination_path: The Content Browser path where the asset will be placed
    :return the configured AssetImportTask
    """

    task = unreal.AssetImportTask()
    task.filename = filename
    task.destination_path = destination_path

    # By default, destination_name is the filename without the extension
    if destination_name is not None:
        task.destination_name = destination_name

    task.replace_existing = replace_existing
    task.automated = automated
    task.save = save
    task.async_ = True

    alembic_settings = unreal.AbcImportSettings()

    alembic_settings.conversion_settings = unreal.AbcConversionSettings(
        scale=unreal.Vector(1, -1, 1),  # Set the scale using a Vector (adjust the values accordingly)
        rotation=unreal.Vector(90, 0.0, 0.0)  # Set the rotation using a Vector (adjust the values accordingly)
    )
    alembic_settings.geometry_cache_settings = unreal.AbcGeometryCacheSettings(
        compressed_position_precision=0.001,
    )
    alembic_settings.sampling_settings = unreal.AbcSamplingSettings(
        frame_start=1001,

    )

    alembic_settings.import_type = unreal.AlembicImportType.GEOMETRY_CACHE
    task.options = alembic_settings

    return task


def _generate_alembic_camera_import_task(
    filename,
    destination_path,
    destination_name=None,
    replace_existing=True,
    automated=True,
    save=True,
):
    """
    Create and configure an Unreal AssetImportTask

    :param filename: The fbx file to import
    :param destination_path: The Content Browser path where the asset will be placed
    :return the configured AssetImportTask
    """

    task = unreal.AssetImportTask()
    task.filename = filename
    task.destination_path = destination_path

    # By default, destination_name is the filename without the extension
    if destination_name is not None:
        task.destination_name = destination_name

    task.replace_existing = replace_existing
    task.automated = automated
    task.save = save
    task.async_ = True

    alembic_settings = unreal.AbcImportSettings()
    if True:  # is Houdini? FIX to automatic determine this
        # Assign the Alembic settings to the import task
        # Customize Alembic import settings here if needed
        alembic_settings.conversion_settings = unreal.AbcConversionSettings(
            # scale=unreal.Vector(100, -100, 100),  # Set the scale using a Vector (adjust the values accordingly)
            rotation=unreal.Vector(90, 0.0, 0.0)  # Set the rotation using a Vector (adjust the values accordingly)
        )

    alembic_settings.import_type = unreal.AlembicImportType.GEOMETRY_CACHE
    task.options = alembic_settings

    return task
