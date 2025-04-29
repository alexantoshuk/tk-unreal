# This file is based on templates provided and copyrighted by Autodesk, Inc.
# This file has been modified by Epic Games, Inc. and is subject to the license
# file included in this repository.

from collections import namedtuple, defaultdict
import copy
import os
import sys

import unreal

import sgtk

from pathlib import Path
libs_path = os.path.join(str(Path(__file__).parents[3]), 'libs')
sys.path.insert(0, libs_path)
import unreal_utils


# A named tuple to store LevelSequence edits: the sequence/track/section
# the edit is in.
SequenceEdit = namedtuple("SequenceEdit", ["sequence", "track", "section"])


HookBaseClass = sgtk.get_hook_baseclass()


class UnrealSessionCollector(HookBaseClass):
    """
    Collector that operates on the Unreal session. Should inherit from the basic
    collector hook.

    You can read more about collectors here:
    http://developer.shotgunsoftware.com/tk-multi-publish2/collector.html

    Here's Maya's implementation for reference:
    https://github.com/shotgunsoftware/tk-maya/blob/master/hooks/tk-multi-publish2/basic/collector.py
    """

    @property
    def settings(self):
        """
        Dictionary defining the settings that this collector expects to receive
        through the settings parameter in the process_current_session and
        process_file methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """

        # grab any base class settings
        collector_settings = super(UnrealSessionCollector, self).settings or {}

        # Add setting specific to this collector.
        work_template_setting = {
            "Work Template": {
                "type": "template",
                "default": None,
                "description": "Template path for artist work files. Should "
                               "correspond to a template defined in "
                               "templates.yml. If configured, is made available"
                               "to publish plugins via the collected item's "
                               "properties. ",
            },
        }

        collector_settings.update(work_template_setting)

        return collector_settings

    def process_current_session(self, settings, parent_item):
        """
        Analyzes the current session in Unreal and parents a subtree of
        items under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """

        # Create an item representing the current Unreal session
        parent_item = self.collect_current_session(settings, parent_item)

        actors = folders = None
        assets = self.collect_selected_assets(parent_item)

        if not assets:
            folders = self.collect_selected_movie_scene_folders(parent_item)
            actors = self.collect_selected_actors(parent_item)

        if (not assets) and (not actors) and (not folders):
            self.collect_rendered_movies(parent_item)

    def collect_current_session(self, settings, parent_item):
        """
        Creates an item that represents the current Unreal session.

        :param dict settings: Configured settings for this collector
        :param parent_item: Parent Item instance

        :returns: Item of type unreal.session
        """
        # Create the session item for the publish hierarchy
        # In Unreal, the current session can be defined as the current level/map (.umap)
        # Don't create a session item for now since the .umap does not need to be published
        session_item = parent_item

        # Get the icon path to display for this item
        icon_path = os.path.join(
            self.disk_location,
            os.pardir,
            "icons",
            "unreal.png"
        )

        # Set the icon for the session item
        # Will also be used for the children items parented to the session item
        session_item.set_icon_from_path(icon_path)

        # Set the project root
        engine = sgtk.platform.current_engine()
        unreal_sg = engine.unreal_sg_engine
        project_root = unreal_sg.get_shotgrid_work_dir()

        # Important to convert "/" in path returned by Unreal to "\" for templates to work
        project_root = project_root.replace("/", "\\")
        session_item.properties["project_root"] = project_root

        self.logger.info("Current Unreal project folder is: %s." % (project_root))

        # If a work template is defined, add it to the item properties so
        # that it can be used by publish plugins
        work_template_setting = settings.get("Work Template")
        if work_template_setting:
            publisher = self.parent
            work_template = publisher.get_template_by_name(work_template_setting.value)

            if work_template:
                # Override the work template to use the project root from Unreal and not the default root for templates
                work_template = sgtk.TemplatePath(work_template.definition, work_template.keys, project_root)

                session_item.properties["work_template"] = work_template
                self.logger.debug("Work template defined for Unreal collection.")

        self.logger.info("Collected current Unreal session")

        return session_item

    def collect_selected_assets(self, parent_item):
        """
        Creates items for assets selected in Unreal.

        :param parent_item: Parent Item instance
        """
        unreal_sg = sgtk.platform.current_engine().unreal_sg_engine
        sequence_edits = None
        # Iterate through the selected assets and get their info and add them as items to be published
        n = 0
        for asset in unreal_sg.selected_assets:
            # if asset.asset_class_path.asset_name == "LevelSequence":
            #     if sequence_edits is None:
            #         sequence_edits = self.retrieve_sequence_edits()
            #     self.collect_level_sequence(parent_item, asset, sequence_edits)
            # else:
            if self.create_asset_item(
                parent_item,
                # :class:`Name` instances, we cast them to strings otherwise
                # string operations fail down the line..
                "%s" % unreal_sg.object_path(asset),
                "%s" % asset.asset_class_path.asset_name,
                "%s" % asset.asset_name,
            ):
                n += 1
        return n

    def create_asset_item(self, parent_item, asset_path, asset_type, asset_name, display_name=None):
        """
        Create an unreal item under the given parent item.

        :param asset_path: The unreal asset path, as a string.
        :param asset_type: The unreal asset type, as a string.
        :param asset_name: The unreal asset name, as a string.
        :param display_name: Optional display name for the item.
        :returns: The created item.
        """
        item_type = "unreal.asset.%s" % asset_type
        asset_item = parent_item.create_item(
            item_type,  # Include the asset type for the publish plugin to use
            asset_type,  # Display type
            display_name or asset_name,  # Display name of item instance
        )

        ctx = unreal_utils.ctx_from_asset_path(os.path.dirname(asset_path))
        unreal.log(f"Try to get SG Context from asset path")
        if ctx:
            _type, code, step = ctx
            unreal.log(f"Determine SG Context items: ASSET_TYPE: {_type}, ASSET: {code}, PIPE_STEP: {step}")
            context = unreal_utils.create_asset_context(_type, code, step)
            if context:
                unreal.log(f"Get SG Context from asset path: {context} {context.to_dict()} ")
                asset_item.properties["context"] = context
            else:
                self.logger.error(f"Can't find task with step '{step}' for asset '{code}'")
                asset_item.properties["context"] = asset_item.context
        else:
            unreal.log(f"SG Context: None")
            asset_item.properties["context"] = asset_item.context

        # asset_item.properties["ctx"] = ctx
        # Set asset properties which can be used by publish plugins
        asset_item.properties["asset_path"] = asset_path
        asset_item.properties["asset_name"] = asset_name
        asset_item.properties["asset_type"] = asset_type
        return asset_item

    def collect_selected_actors(self, parent_item):
        """
        Creates items for assets selected in Unreal.

        :param parent_item: Parent Item instance
        """

        actor_system = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        selected_actors = actor_system.get_selected_level_actors()

        unreal_sg = sgtk.platform.current_engine().unreal_sg_engine
        if unreal_sg.selected_assets:
            return
        # Iterate through the selected assets and get their info and add them as items to be published
        active_level_sequence = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()

        n = 0
        for actor in selected_actors:
            display_name = actor_name = actor.get_actor_label()
            binding = unreal_utils.find_actor_sequence_binding(active_level_sequence, actor_name)
            if binding:
                seq = binding.sequence
                display_name = f"{actor_name}\n({seq.get_name()})"

            if self.create_actor_item(
                parent_item,
                # :class:`Name` instances, we cast them to strings otherwise
                # string operations fail down the line..
                actor,
                "%s" % actor.get_class().get_name(),
                binding,
                "%s" % actor_name,
                display_name,
            ):
                n += 1
        return n

    def create_actor_item(self, parent_item, actor, actor_type, binding, actor_name, display_name=None):
        """
        Create an unreal item under the given parent item.

        :param actor_path: The unreal actor path, as a string.
        :param actor_type: The unreal actor type, as a string.
        :param actor_name: The unreal actor name, as a string.
        :param display_name: Optional display name for the item.
        :returns: The created item.
        """

        item_type = "unreal.actor.%s" % actor_type
        actor_item = parent_item.create_item(
            item_type,  # Include the asset type for the publish plugin to use
            actor_type,  # Display type
            display_name or actor_name,  # Display name of item instance
        )

        ctx = None
        if binding:
            ctx = unreal_utils.ctx_from_sequence(binding.sequence)
            unreal.log(f"Try to get SG Context from sequence name")
        else:
            lvl = actor.get_level()
            ctx = unreal_utils.ctx_from_level(lvl)
            unreal.log(f"Try to get SG Context from level name")

        if ctx:
            scene, shot, step = ctx
            task_name = None
            if 'camera' in actor_name.lower():
                task_name = 'Camera'
            unreal.log(f"Determine SG Context items: SCENE: {scene}, SHOT: {shot}, PIPE_STEP: {step}, TASK_NAME: {task_name}")
            context = unreal_utils.create_shot_context(scene, shot, step, task_name)
            if context:
                unreal.log(f"SG Context: {context} {context.to_dict()} ")
                actor_item.properties["context"] = context
            else:
                self.logger.error(f"Can't find task with step '{step}' for shot '{shot}'")
                actor_item.properties["context"] = actor_item.context
        else:
            unreal.log(f"SG Context: None")
            actor_item.properties["context"] = actor_item.context
        # actor_item.properties["ctx"] = ctx

        # Set asset properties which can be used by publish plugins
        actor_item.properties["actor"] = actor
        actor_item.properties["actor_name"] = actor_name
        actor_item.properties["actor_type"] = actor_type
        actor_item.properties["binding"] = binding

        return actor_item

    def collect_selected_movie_scene_folders(self, parent_item):
        """
        Creates items for all actors found in selected movie scene folders.
        Actors in one folder will be exported to one FBX with folder's name.
        :param parent_item: Parent Item instance
        """
        unreal_sg = sgtk.platform.current_engine().unreal_sg_engine
        if unreal_sg.selected_assets:
            return

        sel_folders = unreal.LevelSequenceEditorBlueprintLibrary.get_selected_folders()
        n = 0

        sel_actors = unreal_utils.get_bound_actors(unreal.LevelSequenceEditorBlueprintLibrary.get_selected_bindings())
        sel_actors_names = set(a.get_full_name() for a in sel_actors)

        def skip_folder(bindings, actors_names):
            if not bindings:
                return True

            for binding in bindings:
                a = unreal_utils.get_bound_actor(binding)
                if a and (a.get_full_name() in actors_names):
                    return True
            return False

        for folder in sel_folders:
            display_name = folder_name = folder.get_folder_name()
            bindings = folder.get_child_object_bindings()

            if skip_folder(bindings, sel_actors_names):
                continue

            if self.create_movie_scene_folder_item(
                parent_item,
                folder,
                "%s" % folder_name,
                display_name,
            ):
                n += 1
        return n

    def create_movie_scene_folder_item(self, parent_item, folder, folder_name, display_name=None):
        """
        """
        bindings = folder.get_child_object_bindings()
        if not bindings:
            return

        item_type = "unreal.movie_scene_folder"
        folder_item = parent_item.create_item(
            item_type,  # Include the asset type for the publish plugin to use
            "MovieSceneFolder",  # Display type
            display_name or folder_name,  # Display name of item instance
        )
        ctx = None

        for binding in bindings:
            if not ctx:
                ctx = unreal_utils.ctx_from_sequence(binding.sequence)
                unreal.log(f"Try to get SG Context from sequence name")

        if ctx:
            scene, shot, step = ctx
            unreal.log(f"Determine SG Context items: SCENE: {scene}, SHOT: {shot}, PIPE_STEP: {step}")
            context = unreal_utils.create_shot_context(scene, shot, step)
            if context:
                unreal.log(f"SG Context: {context} {context.to_dict()} ")
                folder_item.properties["context"] = context
            else:
                self.logger.error(f"Can't find task with step '{step}' for shot '{shot}'")
                folder_item.properties["context"] = folder_item.context
        else:
            unreal.log(f"SG Context: None")
            folder_item.properties["context"] = folder_item.context

        folder_item.properties["bindings"] = bindings
        folder_item.properties["folder_name"] = folder_name
        icon_path = os.path.join(self._icons_dir(), "folder.png")
        folder_item.set_icon_from_path(icon_path)
        return folder_item

    def collect_rendered_movies(self, parent_item):
        """
        Creates items for found rendered movies.

        :param parent_item: Parent Item instance
        """

        movies_dir = os.path.join(unreal_utils.PROJECT_ROOT, "render")
        unreal.log(f"Collect rendered movies from '{movies_dir}'...")
        for (dirpath, dirnames, filenames) in os.walk(movies_dir):
            # filenames = (os.path.join(dirpath, f) for f in filenames)
            # for f in unreal_utils.last_versions(filenames):
            for f in filenames:
                filename = os.path.join(dirpath, f)
                self.create_rendered_movie_item(parent_item, filename)

            for d in dirnames:
                dirname = os.path.join(dirpath, d)
                self.create_rendered_exr_sequence_item(parent_item, dirname)

            break

    def create_rendered_movie_item(self, parent_item, movie_path, display_name=None):
        """
        Create an unreal item under the given parent item.

        :param asset_path: The unreal asset path, as a string.
        :param asset_type: The unreal asset type, as a string.
        :param asset_name: The unreal asset name, as a string.
        :param display_name: Optional display name for the item.
        :returns: The created item.
        """
        asset_type = "Rendered Movie"
        item_type = "unreal.render.mov"
        name = os.path.basename(movie_path)
        if not display_name:
            display_name = name

        _, ext = os.path.splitext(movie_path)
        if ext.lower() != '.mov':
            unreal.log(f"SG Publish collector: ignore non-mov file '{movie_path}'")
            return

        ctx = unreal_utils.ctx_from_movie_path(movie_path)

        unreal.log(f"Try to get SG Context from movie '{movie_path}' ")
        if ctx:
            scene, shot, step = ctx
            unreal.log(f"Determine SG Context items: SCENE: {scene}, SHOT: {shot}, PIPE_STEP: {step}")

            context = unreal_utils.create_shot_context(scene, shot, step)
            if not context:
                context = unreal_utils.create_shot_context(scene, shot, "LAY")

            if context:
                unreal.log(f"Get SG Context from movie path: {context} {context.to_dict()} ")
                mov_item = parent_item.create_item(
                    item_type,  # Include the asset type for the publish plugin to use
                    asset_type,  # Display type
                    display_name,  # Display name of item instance
                )
                mov_item.properties["context"] = context
            else:
                unreal.log_error(f"Can't find task with step '{step}' for shot '{shot}'")
                return

        else:
            unreal.log(f"SG Context: None")
            return

        name, ext = os.path.splitext(name)
        mov_item.properties["movie_path"] = movie_path
        mov_item.properties["name"] = name
        # mov_item.properties["ctx"] = ctx
        # Set asset properties which can be used by publish plugins
        icon_path = os.path.join(self._icons_dir(), "movie.png")
        mov_item.set_icon_from_path(icon_path)

        return mov_item

    def create_rendered_exr_sequence_item(self, parent_item, seq_dir_path, display_name=None):
        """
        Create an unreal item under the given parent item.

        :param asset_path: The unreal asset path, as a string.
        :param asset_type: The unreal asset type, as a string.
        :param asset_name: The unreal asset name, as a string.
        :param display_name: Optional display name for the item.
        :returns: The created item.
        """

        first = unreal_utils.find_first_seuence_file(seq_dir_path, ext='.exr')
        if not first:
            return

        try:
            _display_name = unreal_utils.filename_as_sequence_pattern(first)
        except:
            unreal.log(f"SG Publish collector: invalid sequence file name '{first}'")
            return

        asset_type = "Rendered EXR Sequence"
        item_type = "unreal.render.exr"
        name = os.path.basename(seq_dir_path)

        if not display_name:
            display_name = os.path.basename(_display_name)

        ctx = unreal_utils.ctx_from_movie_path(seq_dir_path)

        unreal.log(f"Try to get SG Context from sequence dir name '{seq_dir_path}' ")
        if ctx:
            scene, shot, step = ctx
            unreal.log(f"Determine SG Context items: SCENE: {scene}, SHOT: {shot}, PIPE_STEP: {step}")

            context = unreal_utils.create_shot_context(scene, shot, step)
            if not context:
                context = unreal_utils.create_shot_context(scene, shot, "LAY")

            if context:
                unreal.log(f"Get SG Context from movie path: {context} {context.to_dict()} ")
                mov_item = parent_item.create_item(
                    item_type,  # Include the asset type for the publish plugin to use
                    asset_type,  # Display type
                    display_name,  # Display name of item instance
                )
                mov_item.properties["context"] = context
            else:
                unreal.log_error(f"Can't find task with step '{step}' for shot '{shot}'")
                return

        else:
            unreal.log(f"SG Context: None")
            return

        name, ext = os.path.splitext(name)
        mov_item.properties["movie_path"] = seq_dir_path
        mov_item.properties["name"] = name
        # mov_item.properties["ctx"] = ctx
        # Set asset properties which can be used by publish plugins
        icon_path = os.path.join(self._icons_dir(), "image_sequence.png")
        mov_item.set_icon_from_path(icon_path)

        return mov_item

    def get_all_paths_from_sequence(self, level_sequence, sequence_edits, visited=None):
        """
        Retrieve all edit paths from the given Level Sequence to top Level Sequences.

        Recursively explore the sequence edits, stop the recursion when a Level
        Sequence which is not a sub-sequence of another is reached.

        Lists of Level Sequences are returned, where each list contains all the
        the Level Sequences to traverse to reach the top Level Sequence from the
        starting Level Sequence.

        For example if a master Level Sequence contains some `Seq_<seq number>`
        sequences and each of them contains shots like `Shot_<seq number>_<shot number>`,
        a path for Shot_001_010 would be `[Shot_001_010, Seq_001, Master sequence]`.

        If an alternate Cut is maintained with another master level Sequence, both
        paths would be detected and returned by this method, e.g.
        `[[Shot_001_010, Seq_001, Master sequence], [Shot_001_010, Seq_001, Master sequence 2]]`

        Maintain a list of visited Level Sequences to detect cycles.

        :param level_sequence: A :class:`unreal.LevelSequence` instance.
        :param sequence_edits: A dictionary with  :class:`unreal.LevelSequence as keys and
                                              lists of :class:`SequenceEdit` as values.
        :param visited: A list of :class:`unreal.LevelSequence` instances, populated
                        as nodes are visited.
        :returns: A list of lists of Level Sequences.
        """
        if not visited:
            visited = []
        visited.append(level_sequence)
        self.logger.info("Treating %s" % level_sequence.get_name())
        if not sequence_edits[level_sequence]:
            # No parent, return a list with a single entry with the current
            # sequence
            return [[level_sequence]]

        all_paths = []
        # Loop over parents get all paths starting from them
        for edit in sequence_edits[level_sequence]:
            if edit.sequence in visited:
                self.logger.warning(
                    "Detected a cycle in edits path %s to %s" % (
                        "->".join(visited), edit.sequence
                    )
                )
            else:
                # Get paths from the parent and prepend the current sequence
                # to them.
                for edit_path in self.get_all_paths_from_sequence(
                    edit.sequence,
                    sequence_edits,
                    copy.copy(visited),  # Each visit needs its own stack
                ):
                    self.logger.info("Got %s from %s" % (edit_path, edit.sequence.get_name()))
                    all_paths.append([level_sequence] + edit_path)
        return all_paths

    def collect_level_sequence(self, parent_item, asset, sequence_edits):
        """
        Collect the items for the given Level Sequence asset.

        Multiple items can be collected for a given Level Sequence if it appears
        in multiple edits.

        :param parent_item: Parent Item instance.
        :param asset: An Unreal LevelSequence asset.
        :param sequence_edits: A dictionary with  :class:`unreal.LevelSequence as keys and
                                              lists of :class:`SequenceEdit` as values.
        """
        unreal_sg = sgtk.platform.current_engine().unreal_sg_engine
        level_sequence = unreal.load_asset(unreal_sg.object_path(asset))
        for edits_path in self.get_all_paths_from_sequence(level_sequence, sequence_edits):
            # Reverse the path to have it from top master sequence to the shot.
            edits_path.reverse()
            self.logger.info("Collected %s" % [x.get_name() for x in edits_path])
            if len(edits_path) > 1:
                display_name = "%s (%s)" % (edits_path[0].get_name(), edits_path[-1].get_name())
            else:
                display_name = edits_path[0].get_name()
            item = self.create_asset_item(
                parent_item,
                edits_path[0].get_path_name(),
                "LevelSequence",
                edits_path[0].get_name(),
                display_name,
            )
            # Store the edits on the item so we can leverage them later when
            # publishing.
            item.properties["edits_path"] = edits_path

    def retrieve_sequence_edits(self):
        """
        Build a dictionary for all Level Sequences where keys are Level Sequences
        and values the list of edits they are in.

        :returns: A dictionary of :class:`unreal.LevelSequence` where values are
                  lists of :class:`SequenceEdit`.
        """
        sequence_edits = defaultdict(list)
        unreal_sg = sgtk.platform.current_engine().unreal_sg_engine
        level_sequence_class = unreal.TopLevelAssetPath("/Script/LevelSequence", "LevelSequence")
        asset_helper = unreal.AssetRegistryHelpers.get_asset_registry()
        # Retrieve all Level Sequence assets
        all_level_sequences = asset_helper.get_assets_by_class(level_sequence_class)
        for lvseq_asset in all_level_sequences:
            lvseq = unreal.load_asset(unreal_sg.object_path(lvseq_asset), unreal.LevelSequence)
            # Check shots
            for track in lvseq.find_master_tracks_by_type(unreal.MovieSceneCinematicShotTrack):
                for section in track.get_sections():
                    # Not sure if you can have anything else than a MovieSceneSubSection
                    # in a MovieSceneCinematicShotTrack, but let's be cautious here.
                    try:
                        # Get the Sequence attached to the section and check if
                        # it is the one we're looking for.
                        section_seq = section.get_sequence()
                        sequence_edits[section_seq].append(
                            SequenceEdit(lvseq, track, section)
                        )
                    except AttributeError:
                        pass
        return sequence_edits

    def _icons_dir(self):
        return os.path.join(self.disk_location, os.pardir, os.pardir, os.pardir, "icons")
