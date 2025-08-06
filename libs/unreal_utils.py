import unreal
import os
import sys
import glob
import subprocess
import shutil
from PySide6.QtWidgets import QApplication, QMessageBox

SHOT_SEQUENCE_START = 1001
PROJECT_ROOT = os.path.normpath(unreal.SystemLibrary.get_project_directory())


def msg_box(title, text, buttons=QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setStandardButtons(buttons)
    return msg.exec()  # QMessageBox.Ok, QMessageBox.Cancel


def entity_field_values(name, default=None, context=None):
    import sgtk
    en = sgtk.platform.current_engine()
    ctx = context if context else en.context
    sg = en.shotgun

    entity_type = ctx.entity['type']
    entity_id = ctx.entity['id']

    field_val = sg.find_one(
        entity_type, [["id", "is", entity_id]], [name])
    if field_val:
        field_val = field_val.get(name, default)
    if field_val is None:
        return default
    return field_val


def frame_range_sync(seq, sgctx):
    import sgtk
    en = sgtk.platform.current_engine()
    sg = en.shotgun
    entity_type = ctx.entity['type']
    entity_id = ctx.entity['id']
    field_val = sg.find_one(
        entity_type, [["id", "is", entity_id]], ['sg_edit_handles', 'sg_cut_in', 'sg_cut_out'])

    sg_edit_handles = field_val.get('sg_edit_handles', 0)
    sg_start = field_val.get('sg_edit_handles', 1) - sg_edit_handles
    sg_end = field_val.get('sg_edit_handles', 120) + sg_edit_handles

    cur_start = seq.get_playback_start()
    cur_end = seq.get_playback_end()

    result = True
    if (cur_start, cur_end) != (sg_start, sg_end):
        btn = msg_box("Invalid frame range",
                      f"Puplished sequence frame range is: {cur_start}-{cur_end}\nBut SG frame range is: {sg_start}-{sg_end}",
                      buttons=QMessageBox.StandardButton.Abort | QMessageBox.StandardButton.Ignore)
        result = btn != QMessageBox.Abort
    return result


def update_status():
    import sgtk
    en = sgtk.platform.current_engine()
    ctx = en.context
    sg = en.shotgun

    current_status = sg.find_one(
        "Task", [["id", "is", ctx.task['id']]], ['sg_status_list'])
    if current_status:
        current_status = current_status.get('sg_status_list')

    if current_status in ('fin', 'clsd'):
        return
    new_status = 'rev'
    try:
        sg.update("Task", ctx.task['id'], {'sg_status_list': new_status})
    except:
        sys.stderr.write(
            "WARNING: Can't update task status to '{0}' from this user.\n".format(new_status))


def tk_root():
    import sgtk
    en = sgtk.platform.current_engine()
    ctx = en.context
    root = os.path.dirname(ctx.sgtk.roots.get('primary'))
    return os.path.join(root, 'playsense-cgi-tk')


scripts_path = os.path.join(tk_root(), "scripts")
sys.path.insert(0, scripts_path)


def ffmpeg_path():
    ffmpeg = os.path.join(tk_root(), 'app', 'Windows', 'ffmpeg', 'bin', 'ffmpeg.exe')
    if not os.path.isfile(ffmpeg):
        ffmpeg = shutil.which("ffmpeg")
    unreal.log(f"FFmpeg Path: {ffmpeg}")
    return ffmpeg


FFMPEG_PATH = ffmpeg_path()


def project_field_value(name, default=None, context=None):
    import sgtk
    en = sgtk.platform.current_engine()
    ctx = context if context else en.context
    sg = en.shotgun

    field_val = sg.find_one(
        "Project", [["id", "is", ctx.project['id']]], [name])
    if field_val:
        field_val = field_val.get(name, default)
    if field_val is None:
        return default
    return field_val


def find_first_seuence_file(seq_dir_path, ext='.exr'):
    dirname = os.path.basename(seq_dir_path)
    for (_, _, filenames) in os.walk(seq_dir_path):
        for f in filenames:
            basename, _ext = os.path.splitext(f)
            if _ext.lower() != ext:
                unreal.log(f"SG Publish collector: ignore not '{ext}' seqence dir '{seq_dir_path}'")
                return
            if not f.startswith(dirname):
                unreal.log(f"SG Publish collector: ignore non-conventional EXR seqence dir '{seq_dir_path}'")
                return
            return os.path.join(seq_dir_path, f)
        unreal.log(f"SG Publish collector: ignore empty dir '{seq_dir_path}'")
        return
    return


def filename_as_sequence_pattern(filename):
    splitted = filename.split('.')
    frame = splitted[-2]
    iframe = int(frame)
    splitted[-2] = "#" * len(frame)
    return '.'.join(splitted)


def convert_mov_to_mp4(src, dst):
    commands = [
        FFMPEG_PATH,
        "-i",
        src,
        "-vcodec",
        "libx264",
        "-acodec",
        "libfaac",
        "-pix_fmt",
        "yuv420p",
        dst,
    ]

    if subprocess.run(commands).returncode == 0:
        print("FFmpeg Script Ran Successfully")
        return True
    else:
        print("There was an error running your FFmpeg script")
        return False


def convert_exr_seq_to_mp4(src, dst, fromspace='ACES - ACEScg', fps=30):
    import seq2mov
    seq2mov.convert(filename=src, out_filename=dst, fromspace=fromspace, fps=fps)


def last_versions(filenames, pattern="???.mov"):
    _filenames = set(f[:-len(pattern)] + pattern for f in filenames)
    files = []
    for f in _filenames:
        l = sorted(glob.iglob(f))
        if not l:
            continue
        files.append(l[-1])

    return files


def cleanup_versions(filepath, pattern="???.abc", max_versions=5, logger=None):
    # limit number of versions to max_versions
    if max_versions <= 0:
        return

    pattern = filepath[:-len(pattern)] + pattern
    files = []
    for f in sorted(glob.iglob(pattern))[:-max_versions]:
        try:
            os.remove(f)
            files.append()
            if logger:
                logger.info(
                    "Remove '{0}' because of version limit = {1}".format(f, max_versions))
        except:
            if logger:
                logger.info("Can't remove '{0}'".format(f))


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


def find_spawnables(sequence, actor_name):
    for track in sequence.get_spawnables():
        if track.get_display_name() == actor_name:
            return track
    return None


def find_actor(actor_name, actor_class=unreal.GeometryCacheActor):
    # Check if an actor with the same name already exists in the level
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, actor_class):
        if actor.get_actor_label() == actor_name:
            return actor
    return None


def find_actor_sequence_binding(seq, actor_name):
    if not seq:
        return

    def walk(seq):
        for b in seq.get_bindings():
            # unreal.log(f"NAME: {b.get_name()}  {actor_name}")
            if b.get_name() == actor_name:
                return b

        for track in seq.get_tracks():
            for section in track.get_sections():
                try:
                    b = walk(section.get_sequence())
                    if b:
                        return b
                except:
                    pass
    return walk(seq)


def get_bound_actors(bindings):
    data = []
    for binding in bindings:
        actor = get_bound_actor(binding)
        if actor:
            data.append(actor)
    return data


def get_bound_actor(binding):
    seq = binding.sequence
    binding_id = seq.get_binding_id(binding)
    actors = unreal.LevelSequenceEditorBlueprintLibrary.get_bound_objects(binding_id)
    if actors:
        return actors[0]
    return None


def get_properties(objects, props):
    data = {}
    for o in objects:
        props_dict = {}
        for propname in props:
            try:
                props_dict[propname] = o.get_editor_property(propname)
            except:
                pass
        data[o] = props_dict
    return data


def set_properties(objects, props):
    for o in objects:
        name = o.get_actor_label()
        for propname, value in props.items():
            try:
                o.set_editor_property(propname, value)
                unreal.log(f"Set '{name}' property '{propname}' to '{value}'")
            except:
                pass


def restore_properties(props_data):
    for o, props in props_data.items():
        name = o.get_actor_label()
        for propname, value in props.items():
            try:
                o.set_editor_property(propname, value)
                unreal.log(f"Set '{name}' property '{propname}' to '{value}'")
            except:
                pass


def save_active_state(bindings):
    data = {
        binding: {
            track: [
                (section, section.is_active())
                for section in track.get_sections()
            ]
            for track in binding.get_tracks()
        }
        for binding in bindings
    }
    return data


def restore_active_state(data):
    for tracks_data in data.values():
        for sections in tracks_data.values():
            for (section, active) in sections:
                section.set_is_active(active)


def save_state_and_bake(bindings):
    # selected_bindings = unreal.LevelSequenceEditorBlueprintLibrary.get_selected_bindings()

    data = save_active_state(bindings)
    unreal.log(f"Save state of tracks before baking for bindings: {data}")
    if not data:
        return []
    binding = next(iter(data))
    # bake_transforms
    start_frame = binding.sequence.get_playback_start()
    end_frame = binding.sequence.get_playback_end()
    bake_settings = unreal.BakingAnimationKeySettings(
        baking_key_settings=unreal.BakingKeySettings.ALL_FRAMES,
        frame_increment=1,
        reduce_keys=False,
        start_frame=unreal.FrameNumber(start_frame),
        end_frame=unreal.FrameNumber(end_frame),
        tolerance=0.001)

    # active_level_sequence = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
    focused_level_sequence = unreal.LevelSequenceEditorBlueprintLibrary.get_focused_level_sequence()
    # if focused_level_sequence != binding.sequence:
    #     unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(binding.sequence)

    unreal.log(f"Start baking of transforms for bindings: {bindings}")
    bake_ok = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem).bake_transform_with_settings(bindings, bake_settings)  # , params=unreal.MovieSceneTimeUnit.TICK_RESOLUTION)

    return data


def restore_state_after_bake(data):
    # restore active state
    restore_active_state(data)
    # remove bake transform
    for (binding, tracks_data) in data.items():
        baked_transform_tracks = set(binding.get_tracks()).difference(tracks_data.keys())
        if not baked_transform_tracks:
            unreal.log_warning(f"Can't find baked transform for binding: '{binding.get_name()}'. Skip deletion.")
        for t in baked_transform_tracks:
            binding.remove_track(t)


# def get_version(name):
#     name, ok, ver = name.rpartition(' v')
#     if not ok:
#         return 0
#     try:
#         return int(ver)
#     except:
#         return None


# def set_version(name, ver):
#     _name, ok, _ = name.rpartition(' v')
#     if ok:
#         return f"{_name} v{int(ver)}"
#     return f"{name} v{int(ver)}"


# def up_version(name):
#     _name, ok, ver = name.rpartition(' v')
#     if not ok:
#         ver = 0
#     else:
#         ver = int(ver)
#         name = _name

#     ver += 1
#     return f"{name} v{ver}"


def ctx_from_asset_path(path):
    # /Game/Assets/Prop/SM_Gun/SM_Gun
    splitted = path.split('/')
    if splitted[:3] in (['', 'Game', 'Assets'], ['', 'Game', 'assets']):
        if len(splitted) >= 6:
            asset_type, code, step = splitted[3:6]
        elif len(splitted) == 5:
            asset_type, code = splitted[3:5]
            step = 'MDL'

        return asset_type, code, step

    return None


def ctx_from_shot_path(path):
    splitted = path.split('/')
    if splitted[:3] in (['', 'Game', 'Scenes'], ['', 'Game', 'scenes']):
        if len(splitted) >= 6:
            scn, shot, step = splitted[3:6]
            return scn, shot, step

    return None


def ctx_from_movie_path(path):
    base, ext = os.path.splitext(path)
    # if ext.lower() not in ('.mov'):
    #     return

    name = os.path.basename(path).split(".")[0]
    splitted = name.split("_", 2)
    if len(splitted) < 2:
        return

    scene = splitted[0]
    shot = "_".join(splitted[:2])
    try:
        task = splitted[2]
        return scene, shot, "LGT", task
    except:
        return scene, shot, "LGT", "Lighting"


def ctx_from_sequence(seq):
    seq_name = seq.get_name()
    seq_name = seq_name.rstrip('_sub')
    l = seq_name.split('_')
    if len(l) != 3:
        return None
    scene, code, step = l
    code = '_'.join((scene, code))
    return scene, code, step


def ctx_from_level(level):
    path = level.get_path_name()
    try:
        scene, code, step = path.split('/')[3:6]
        return scene, code, step
    except:
        return None


def step_short_name2(step_id):
    import sgtk
    engine = sgtk.platform.current_engine()

    data = engine.shotgun.find_one("Step", [
        ["id", "is", step_id],
    ],
        fields=["short_name"]
    )
    if data:
        return data["short_name"]


def step_short_name(task_id):
    import sgtk
    engine = sgtk.platform.current_engine()
    step = engine.shotgun.find_one("Task", [
        ["id", "is", task_id],

    ], ["step"])['step']

    step_short_name = engine.shotgun.find_one("Step", [["id", "is", step['id']]], ["short_name"])["short_name"]
    return step_short_name


def sg_asset_type(asset_id):
    import sgtk
    engine = sgtk.platform.current_engine()
    data = engine.shotgun.find_one("Asset", [
        ["id", "is", asset_id],
    ],
        fields=["sg_asset_type"]
    )
    if data:
        return data["sg_asset_type"]


def ctx_from_context(context):
    entity = context.entity
    step = context.step

    step_shortname = None

    if (not entity) or (not step):
        return

    step_id = step["id"]

    entity_type = entity.get("type")
    if entity_type == "Shot":
        shot = entity.get("code", entity.get("name"))
        if not shot:
            return
        scene = shot.split("_", 1)[0]
        step_shortname = step_short_name2(step_id)
        if not step_shortname:
            step_shortname = "LAY"
        return scene, shot, step_shortname

    elif entity_type == "Asset":
        asset = entity.get("code", entity.get("name"))
        if not asset:
            return
        asset_type = sg_asset_type(entity["id"])
        if not asset_type:
            asset_type = "Prop"
        step_shortname = step_short_name2(step_id)
        if not step_shortname:
            step_shortname = "MDL"
        return asset_type, asset, step_shortname


def last_published_info(ctx, published_name):
    import sgtk
    engine = sgtk.platform.current_engine()
    d = ctx.to_dict()
    project = d['project']
    entity = d['entity']

    data = engine.shotgun.find_one("PublishedFile", [
        ["project", "is", project],
        ["entity", "is", entity],
        ["name", "is", published_name],
    ],
        fields=["version_number", "updated_at"],
        order=[
            {'field_name': 'version_number', 'direction': 'desc'},
    ]
    )
    return data


def last_published_version(ctx, published_name):
    import sgtk
    engine = sgtk.platform.current_engine()
    d = ctx.to_dict()
    project = d['project']
    entity = d['entity']

    data = engine.shotgun.find_one("PublishedFile", [
        ["project", "is", project],
        ["entity", "is", entity],
        ["name", "is", published_name],
    ],
        fields=["version_number"],
        order=[
            {'field_name': 'version_number', 'direction': 'desc'},
    ]
    )
    if data:
        return data.get("version_number")


def create_asset_context(asset_type, asset, step=None, task_name=None):
    import sgtk
    engine = sgtk.platform.current_engine()

    ctx = engine.context
    asset = engine.shotgun.find_one("Asset", [
        ["project", "is", ctx.project],
        ["sg_asset_type", "is", asset_type],
        ["code", "is", asset],
    ])
    if not asset:
        return

    task_data = None
    if task_name:
        task_data = engine.shotgun.find_one("Task", [
            ["entity", "is", asset],
            ["content", "is", task_name],
        ], ["name", "content", "step.Step.short_name"])

    if not task_data:
        task_data = engine.shotgun.find_one("Task", [
            ["step.Step.short_name", "is", step],
            ["entity", "is", asset],
        ], ["name", "content", "step.Step.short_name"])

    if not task_data:
        return

    ctx = engine.sgtk.context_from_entity("Task", task_data["id"])
    return ctx


def create_shot_context(scene, shot, step=None, task_name=None):
    import sgtk
    engine = sgtk.platform.current_engine()

    ctx = engine.context
    shot = engine.shotgun.find_one("Shot", [
        ["project", "is", ctx.project],
        ["sg_sequence.Sequence.code", "is", scene],
        ["code", "is", shot],
    ])
    if not shot:
        return

    task_data = None
    if task_name:
        task_data = engine.shotgun.find_one("Task", [
            ["entity", "is", shot],
            ["content", "is", task_name],
        ], ["name", "content", "step.Step.short_name"])

    if not task_data:
        task_data = engine.shotgun.find_one("Task", [
            ["step.Step.short_name", "is", step],
            ["entity", "is", shot],
        ], ["name", "content", "step.Step.short_name"])

    if not task_data:
        return

    ctx = engine.sgtk.context_from_entity("Task", task_data["id"])
    return ctx


def unreal_import_alembic_asset(input_path, destination_path, destination_name, automated=True, create_actor=False):
    """
    Import an ABC into Unreal Content Browser

    :param input_path: The alembic file to import
    :param destination_path: The Content Browser path where the asset will be placed
    :param destination_name: The asset name to use; if None, will use the filename without extension
    """
    unreal.log(f"Destination path: {destination_path}")
    tasks = []
    tasks.append(_generate_alembic_import_task(input_path, destination_path, destination_name, automated=automated))

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

    task = tasks[0]

    if not task.imported_object_paths:
        unreal.log_warning("No objects were imported")
        return None

    unreal.log(f"Import Task for: {task.filename}")
    geometry_cache_path = task.imported_object_paths[0]
    unreal.log(f"Imported object: {geometry_cache_path}")

    if create_actor:
        ctx = ctx_from_shot_path(destination_path)
        scn, shot, step = ctx
        level_name = f"{shot}_{step}"
        seq_name = f"{shot}_{step}_sub"

        seq = unreal.load_asset(f"{destination_path}/{seq_name}")

        if seq and find_possessable(seq, destination_name):
            unreal.log(f"Geometry Cache track '{destination_name}' exists. Skip creation.")
            return geometry_cache_path

        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(f"{destination_path}/{level_name}")
        # unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(seq)

        actor = find_actor(destination_name, unreal.GeometryCacheActor)
        if actor:
            unreal.log(f"Geometry Cache actor '{destination_name}' exists. Replace it.")
            actor.destroy_actor()
            # return geometry_cache_path

        geometry_cache = unreal.load_asset(geometry_cache_path)

        # Spawn the Geometry Cache actor
        geometry_cache_actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_object(geometry_cache, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
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


def unreal_import_vdb(input_path, destination_path, destination_name, automated=False, create_actor=False):
    """
    Import an VDB Volume into Unreal Content Browser

    :param input_path: The vdb file to import
    :param destination_path: The Content Browser path where the asset will be placed
    :param destination_name: The asset name to use; if None, will use the filename without extension
    """

    unreal.log(f"Destination name: {destination_name}")
    unreal.log(f"Destination path: {destination_path}")
    tasks = []
    tasks.append(_generate_vdb_import_task(input_path, destination_path, destination_name, automated=automated))

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

    task = tasks[0]

    if not task.imported_object_paths:
        unreal.log_warning("No objects were imported")
        return None

    unreal.log(f"Import Task for: {task.filename}")
    vdb_path = task.imported_object_paths[0]
    unreal.log(f"Imported object: {vdb_path}")

    if create_actor:
        matname = destination_name + "_mat"
        matpath = f"{destination_path}/{matname}"
        try:
            if unreal.EditorAssetLibrary.delete_asset(matpath):
                unreal.log(f"Found asset '{matpath}' exists. Recreate.")
        except:
            pass

        vdb_tex = unreal.load_asset(vdb_path)

        _, start_frame, _ = input_path.rsplit('.', 2)
        start_frame = int(start_frame)
        end_frame = start_frame + vdb_tex.get_num_frames() - 1

        ## create material and assign vdb #########################################################################
        create_material_instance("/Game/assets/fx/vdb/_common/VDB_materials/mm_VDB", destination_path, matname)
        mat = unreal.load_asset(matpath)
        unreal.MaterialEditingLibrary.set_material_instance_sparse_volume_texture_parameter_value(
            mat, "SparseVolumeTexture", vdb_tex
        )
        unreal.EditorAssetLibrary.save_asset(matpath)

        ## create actor and track #################################################################################
        actor_name = destination_name + "_actor"

        ctx = ctx_from_shot_path(destination_path)
        scn, shot, step = ctx
        level_name = f"{shot}_{step}"
        seq_name = f"{shot}_{step}_sub"

        seq = unreal.load_asset(f"{destination_path}/{seq_name}")

        if seq and find_possessable(seq, actor_name):
            unreal.log(f"VDB track '{actor_name}' exists. Skip creation.")
            return vdb_path

        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(f"{destination_path}/{level_name}")
        # unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(seq)

        actor = find_actor(actor_name, unreal.HeterogeneousVolume.static_class())
        if actor:
            unreal.log(f"VDB actor '{actor_name}' exists. Replace it.")
            actor.destroy_actor()
            # return geometry_cache_path

        actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(unreal.HeterogeneousVolume.static_class(), unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        actor.set_actor_label(actor_name)
        actor.set_actor_scale3d(unreal.Vector(100.0, 100.0, 100.0))
        actor.set_actor_rotation(unreal.Rotator(-90.0, 0.0, 0.0), False)
        heterogeneous_volume_component = actor.get_component_by_class(unreal.HeterogeneousVolumeComponent.static_class())

        # add a binding for the actor
        binding = seq.add_possessable(actor)
        binding.set_name(actor_name)
        binding.set_display_name(actor_name)
        unreal.log(f"Add as posessable to sequence '{seq}'")

        component_binding = seq.add_possessable(
            heterogeneous_volume_component)
        component_binding.set_parent(binding)
        track = component_binding.add_track(
            unreal.MovieSceneFloatTrack)
        unreal.log(f"Add component track 'frame'")
        track.set_property_name_and_path(
            "frame", "frame")
        section = track.add_section()
        section.set_start_frame_bounded(0)
        section.set_end_frame_bounded(0)
        channel = section.get_all_channels()[0]

        channel.add_key(unreal.FrameNumber(start_frame), float(start_frame), interpolation=unreal.MovieSceneKeyInterpolation.LINEAR)
        channel.add_key(unreal.FrameNumber(end_frame), float(end_frame), interpolation=unreal.MovieSceneKeyInterpolation.LINEAR)

        heterogeneous_volume_component.set_editor_property("override_materials", [mat])

        unreal.log(f"VDB actor '{actor_name}' added to the level and sequence '{seq_name}'.")
        return vdb_path

    # Focus the Unreal Content Browser on the imported asset
    # unreal.EditorAssetLibrary.sync_browser_to_objects([vdb_asset_path])
    return vdb_path


def _generate_vdb_import_task(
    filename,
    destination_path,
    destination_name=None,
    replace_existing=True,
    automated=False,
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

    return task


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

    binding = find_actor_sequence_binding(seq, cam_name)
    seq = binding.sequence
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

    # unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(seq)
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
    materials=False,
    textures=False,
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
    alembic_settings.material_settings = unreal.AbcMaterialSettings(find_materials=True)

    alembic_settings.import_type = unreal.AlembicImportType.GEOMETRY_CACHE
    task.options = alembic_settings

    return task


def export_asset_to_fbx(filename, asset):
    """
    Export an asset to FBX from Unreal

    :param destination_path: The path where the exported FBX will be placed
    :param actor: The Unreal actor to export to FBX
    """
    # Setup AssetExportTask for non-interactive mode
    task = unreal.AssetExportTask()
    task.object = asset     # the asset to export
    task.filename = filename        # the filename to export as
    task.automated = True           # don't display the export options dialog
    task.replace_identical = True   # always overwrite the output

    # Setup export options for the export task
    task.options = unreal.FbxExportOption()
    task.options.bake_camera_and_light_animation = unreal.MovieSceneBakeType.BAKE_ALL
    task.options.bake_actor_animation = unreal.MovieSceneBakeType.BAKE_ALL
    task.options.collision = False
    task.options.level_of_detail = False
    task.options.map_skeletal_motion_to_root = True
    # task.options.fbx_export_compatibility = fbx_2013
    # task.options.ascii = False
    # task.options.force_front_x_axis = False
    # task.options.vertex_color = True
    # task.options.level_of_detail = True
    # task.options.welded_vertices = True

    # Do the FBX export
    result = unreal.Exporter.run_asset_export_task(task)

    if not result:
        unreal.log_error(f"Failed to export asset '{asset}' to '{filename}'")
        for error_msg in task.errors:
            unreal.log_error(f"{error_msg}")

        return False

    return result


def export_bindings_to_fbx(filename, bindings, bake=True):
    """
    Export an bindings to FBX from Unreal

    :param destination_path: The path where the exported FBX will be placed
    :param actor: The Unreal actor to export to FBX
    """
    def find_skeletal_anim(binding):
        if binding.find_tracks_by_type(unreal.MovieSceneSkeletalAnimationTrack):
            return binding
        for b in binding.get_child_possessables():
            if b.find_tracks_by_type(unreal.MovieSceneSkeletalAnimationTrack):
                return b
        return None

    skeletal_anim = None
    # !temp remove this feature
    # if len(bindings) == 1:
    #     skeletal_anim = find_skeletal_anim(bindings[0])
    actors = get_bound_actors(bindings)
    backup_enable_publish_mode = get_properties(actors, ['Enable Publish Mode'])

    set_properties(actors, {'Enable Publish Mode': True})

    if bake:
        data = save_state_and_bake(bindings)

    try:
        if skeletal_anim:
            # Skeleton anim export mode
            # binding = skeletal_anim
            binding = bindings[0]
            name = binding.get_display_name()
            unreal.log(f"Publish '{name}' as SkeletalAnimation")
            export_option = unreal.AnimSeqExportOption()
            export_option.record_in_world_space = True

            world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            sequence = binding.sequence

            anim_sequence_asset_path = "/Game"
            anim_sequence_asset_name = "__tmp_anim_seq__"

            anim_sequence = unreal.AssetToolsHelpers.get_asset_tools().create_asset(anim_sequence_asset_name, anim_sequence_asset_path, unreal.AnimSequence, None)
            unreal.log(f"Create temp AnimSequence asset '{anim_sequence_asset_path}/{anim_sequence_asset_name}'")
            try:
                result = unreal.SequencerTools().export_anim_sequence(world, sequence, anim_sequence, export_option, binding, create_link=False)
                unreal.log(f"Bake '{name}' into temp AnimSequence asset'{anim_sequence_asset_path}/{anim_sequence_asset_name}'")
                if result:
                    export_asset_to_fbx(filename, anim_sequence)
            finally:
                unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).delete_asset(f"{anim_sequence_asset_path}/{anim_sequence_asset_name}")
                unreal.log(f"Delete temp AnimSequence asset '{anim_sequence_asset_path}/{anim_sequence_asset_name}'")

        else:
            params = unreal.SequencerExportFBXParams()
            params.world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

            params.sequence = bindings[0].sequence
            params.bindings = bindings
            params.fbx_file_name = filename        # the filename to export as

            # Setup export options for the export task
            params.override_options = unreal.FbxExportOption()
            params.override_options.collision = False
            params.override_options.bake_camera_and_light_animation = unreal.MovieSceneBakeType.BAKE_ALL
            params.override_options.bake_actor_animation = unreal.MovieSceneBakeType.BAKE_ALL
            params.override_options.level_of_detail = False
            # These are the default options for the FBX export
            # params.override_options.fbx_export_compatibility = fbx_2013
            # params.override_options.ascii = False
            # params.override_options.force_front_x_axis = False
            # params.override_options.vertex_color = True
            # params.override_options.level_of_detail = True

            # params.override_options.welded_vertices = True
            # params.override_options.map_skeletal_motion_to_root = False

            result = unreal.SequencerTools().export_level_sequence_fbx(params)

    finally:
        if bake:
            restore_state_after_bake(data)
        restore_properties(backup_enable_publish_mode)

    if not result:
        unreal.log_error(f"Failed to export {filename}")
        return result

    return result


def create_material_instance(parent_material_path, path, name):
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

    parent_material = unreal.EditorAssetLibrary.load_asset(parent_material_path)
    if not parent_material:
        unreal.log_error(f"Failed to load parent material: {parent_material_path}")
        return

    material_instance = asset_tools.create_asset(
        asset_name=name,
        package_path=path,
        asset_class=unreal.MaterialInstanceConstant,
        factory=unreal.MaterialInstanceConstantFactoryNew()
    )
    unreal.MaterialEditingLibrary.set_material_instance_parent(material_instance, parent_material)
    unreal.EditorAssetLibrary.save_asset(f"{path}/{name}")
    unreal.log(f"Material Instance '{name}' created and saved at '{path}'")
    material_instance
