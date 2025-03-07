# This file is based on templates provided and copyrighted by Autodesk, Inc.
# This file has been modified by Epic Games, Inc. and is subject to the license
# file included in this repository.

import sgtk
import os
import sys
import unreal
import datetime

from pathlib import Path
libs_path = os.path.join(str(Path(__file__).parents[3]), 'libs')
sys.path.insert(0, libs_path)
import unreal_utils

# Local storage path field for known Oses.
_OS_LOCAL_STORAGE_PATH_FIELD = {
    "darwin": "mac_path",
    "win32": "windows_path",
    "linux": "linux_path",
    "linux2": "linux_path",
}[sys.platform]


HookBaseClass = sgtk.get_hook_baseclass()


class UnrealActorPublishPlugin(HookBaseClass):
    """
    Plugin for publishing an Unreal asset.

    This hook relies on functionality found in the base file publisher hook in
    the publish2 app and should inherit from it in the configuration. The hook
    setting for this plugin should look something like this::

        hook: "{self}/publish_file.py:{engine}/tk-multi-publish2/basic/publish_session.py"

    To learn more about writing a publisher plugin, visit
    http://developer.shotgunsoftware.com/tk-multi-publish2/plugin.html
    """

    # NOTE: The plugin icon and name are defined by the base file plugin.

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        return """Publishes the asset to Shotgun. A <b>Publish</b> entry will be
        created in Shotgun which will include a reference to the exported asset's current
        path on disk. Other users will be able to access the published file via
        the <b>Loader</b> app so long as they have access to
        the file's location on disk."""

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.

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

        # inherit the settings from the base publish plugin
        base_settings = super(UnrealActorPublishPlugin, self).settings or {}

        # Here you can add any additional settings specific to this plugin
        publish_template_setting = {
            "Publish Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published work files. Should"
                               "correspond to a template defined in "
                               "templates.yml.",
            },
            "Publish Folder": {
                "type": "string",
                "default": None,
                "description": "Optional folder to use as a root for publishes"
            },
        }

        # update the base settings
        base_settings.update(publish_template_setting)

        return base_settings

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["unreal.actor.*"]

    def create_settings_widget(self, parent):
        """
        Creates a Qt widget, for the supplied parent widget (a container widget
        on the right side of the publish UI).

        :param parent: The parent to use for the widget being created.
        :returns: A :class:`QtGui.QFrame` that displays editable widgets for
                 modifying the plugin's settings.
        """
        # defer Qt-related imports
        from sgtk.platform.qt import QtGui, QtCore

        # Create a QFrame with all our widgets
        settings_frame = QtGui.QFrame(parent)
        # Create our widgets, we add them as properties on the QFrame so we can
        # retrieve them easily. Qt uses camelCase so our xxxx_xxxx names can't
        # clash with existing Qt properties.

        # Show this plugin description
        settings_frame.description_label = QtGui.QLabel(self.description)
        settings_frame.description_label.setWordWrap(True)
        settings_frame.description_label.setOpenExternalLinks(True)
        settings_frame.description_label.setTextFormat(QtCore.Qt.RichText)

        # Unreal setttings
        settings_frame.unreal_publish_folder_label = QtGui.QLabel("Publish folder:")
        storage_roots = self.parent.shotgun.find(
            "LocalStorage",
            [],
            ["code", _OS_LOCAL_STORAGE_PATH_FIELD]
        )
        settings_frame.storage_roots_widget = QtGui.QComboBox()
        settings_frame.storage_roots_widget.addItem("Current Unreal Project")
        for storage_root in storage_roots:
            if storage_root[_OS_LOCAL_STORAGE_PATH_FIELD]:
                settings_frame.storage_roots_widget.addItem(
                    "%s (%s)" % (
                        storage_root["code"],
                        storage_root[_OS_LOCAL_STORAGE_PATH_FIELD]
                    ),
                    userData=storage_root,
                )
        # Create the layout to use within the QFrame
        settings_layout = QtGui.QVBoxLayout()
        settings_layout.addWidget(settings_frame.description_label)
        settings_layout.addWidget(settings_frame.unreal_publish_folder_label)
        settings_layout.addWidget(settings_frame.storage_roots_widget)

        settings_layout.addStretch()
        settings_frame.setLayout(settings_layout)
        return settings_frame

    def get_ui_settings(self, widget):
        """
        Method called by the publisher to retrieve setting values from the UI.

        :returns: A dictionary with setting values.
        """
        # defer Qt-related imports
        from sgtk.platform.qt import QtCore

        self.logger.info("Getting settings from UI")

        # Please note that we don't have to return all settings here, just the
        # settings which are editable in the UI.
        storage_index = widget.storage_roots_widget.currentIndex()
        publish_folder = None
        if storage_index > 0:  # Something selected and not the first entry
            storage = widget.storage_roots_widget.itemData(storage_index, role=QtCore.Qt.UserRole)
            publish_folder = storage[_OS_LOCAL_STORAGE_PATH_FIELD]

        settings = {
            "Publish Folder": publish_folder,
        }
        return settings

    def set_ui_settings(self, widget, settings):
        """
        Method called by the publisher to populate the UI with the setting values.

        :param widget: A QFrame we created in `create_settings_widget`.
        :param settings: A list of dictionaries.
        :raises NotImplementedError: if editing multiple items.
        """
        # defer Qt-related imports
        from sgtk.platform.qt import QtCore

        self.logger.info("Setting UI settings")
        if len(settings) > 1:
            # We do not allow editing multiple items
            raise NotImplementedError
        cur_settings = settings[0]
        # Note: the template is validated in the accept method, no need to check it here.
        publish_template_setting = cur_settings.get("Publish Template")
        publisher = self.parent
        publish_template = publisher.get_template_by_name(publish_template_setting)
        if isinstance(publish_template, sgtk.TemplatePath):
            widget.unreal_publish_folder_label.setEnabled(False)
            widget.storage_roots_widget.setEnabled(False)
        folder_index = 0
        publish_folder = cur_settings["Publish Folder"]
        if publish_folder:
            for i in range(widget.storage_roots_widget.count()):
                data = widget.storage_roots_widget.itemData(i, role=QtCore.Qt.UserRole)
                if data and data[_OS_LOCAL_STORAGE_PATH_FIELD] == publish_folder:
                    folder_index = i
                    break
            self.logger.debug("Index for %s is %s" % (publish_folder, folder_index))
        widget.storage_roots_widget.setCurrentIndex(folder_index)

    def load_saved_ui_settings(self, settings):
        """
        Load saved settings and update the given settings dictionary with them.

        :param settings: A dictionary where keys are settings names and
                         values Settings instances.
        """
        # Retrieve SG utils framework settings module and instantiate a manager
        fw = self.load_framework("tk-framework-shotgunutils_v5.x.x")
        module = fw.import_module("settings")
        settings_manager = module.UserSettings(self.parent)

        # Retrieve saved settings
        settings["Publish Folder"].value = settings_manager.retrieve(
            "publish2.publish_folder",
            settings["Publish Folder"].value,
            settings_manager.SCOPE_PROJECT
        )
        self.logger.debug("Loaded settings %s" % settings["Publish Folder"])

    def save_ui_settings(self, settings):
        """
        Save UI settings.

        :param settings: A dictionary of Settings instances.
        """
        # Retrieve SG utils framework settings module and instantiate a manager
        fw = self.load_framework("tk-framework-shotgunutils_v5.x.x")
        module = fw.import_module("settings")
        settings_manager = module.UserSettings(self.parent)
        # unreal.log(f"SAVE UI: {settings_manager} {dir(settings_manager)} ")
        # Save settings
        publish_folder = settings["Publish Folder"].value
        settings_manager.store("publish2.publish_folder", publish_folder, settings_manager.SCOPE_PROJECT)

    def accept(self, settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                all. Required.
            - enabled: If True, the plugin will be enabled in the UI, otherwise
                it will be disabled. Optional, True by default.
            - visible: If True, the plugin will be visible in the UI, otherwise
                it will be hidden. Optional, True by default.
            - checked: If True, the plugin will be checked in the UI, otherwise
                it will be unchecked. Optional, True by default.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """

        accepted = True
        publisher = self.parent

        item.context = item.properties["context"]

        # ensure the publish template is defined
        publish_template_setting = settings.get("Publish Template")
        publish_template = publisher.get_template_by_name(publish_template_setting.value)
        if not publish_template:
            self.logger.debug(
                "A publish template could not be determined for the "
                "asset item. Not accepting the item."
            )
            accepted = False

        # we've validated the work and publish templates. add them to the item properties
        # for use in subsequent methods
        item.properties["publish_template"] = publish_template
        self.load_saved_ui_settings(settings)

        return {
            "accepted": accepted,
            "checked": True
        }

    def validate(self, settings, item):
        """
        Validates the given item to check that it is ok to publish. Returns a
        boolean to indicate validity.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :returns: True if item is valid, False otherwise.
        """
        # raise an exception here if something is not valid.
        # If you use the logger, warnings will appear in the validation tree.
        # You can attach callbacks that allow users to fix these warnings
        # at the press of a button.
        #
        # For example:
        #
        # self.logger.info(
        #         "Your session is not part of a maya project.",
        #         extra={
        #             "action_button": {
        #                 "label": "Set Project",
        #                 "tooltip": "Set the maya project",
        #                 "callback": lambda: mel.eval('setProject ""')
        #             }
        #         }
        #     )

        actor = item.properties.get("actor")
        actor_name = item.properties.get("actor_name")
        if not actor or not actor_name:
            self.logger.debug("Actor or name not configured.")
            return False

        publish_template = item.properties["publish_template"]

        # Add the Unreal asset name to the fields
        fields = {"name": actor_name}

        # Add today's date to the fields
        # date = datetime.date.today()
        # fields["YYYY"] = date.year
        # fields["MM"] = date.month
        # fields["DD"] = date.day
        # ctx = item.properties["ctx"]
        # scene, shot, step = ctx
        # fields['Sequence'] = scene
        # fields['Shot'] = shot
        # fields['Step'] = step
        # published_name
        ctx = unreal_utils.ctx_from_context(item.context)
        if ctx:
            scene, shot, step = ctx
            fields['Sequence'] = scene
            fields['Shot'] = shot
            fields['Step'] = step

        # Stash the Unrea asset path and name in properties
        item.properties["actor"] = actor
        item.properties["actor_name"] = actor_name

        # Get destination path for exported FBX from publish template
        # which should be project root + publish template
        fields['version'] = 1
        publish_path = publish_template.apply_fields(fields)
        published_name = os.path.basename(publish_path).replace(".v001", "")

        version = unreal_utils.last_published_version(item.context, published_name)
        if version is not None:
            fields['version'] = version + 1
            publish_path = publish_template.apply_fields(fields)

        publish_path = os.path.normpath(publish_path)
        if not os.path.isabs(publish_path):
            # If the path is not absolute, prepend the publish folder setting.
            publish_folder = settings["Publish Folder"].value
            if not publish_folder:
                publish_folder = unreal.Paths.project_saved_dir()
            publish_path = os.path.abspath(
                os.path.join(
                    publish_folder,
                    publish_path
                )
            )

        item.properties["publish_path"] = publish_path
        item.properties["path"] = publish_path

        # Set the Published File Type
        publish_type = "FBX"
        if "camera" in actor_name.lower():
            publish_type = "FBX Camera"
        item.properties["publish_type"] = publish_type

        # item.properties["publish_version"] = 10

        # run the base class validation
        # return super(UnrealActorPublishPlugin, self).validate(settings, item)
        self.save_ui_settings(settings)
        return True

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # This is where you insert custom information into `item`, like the
        # path of the file being published or any dependency this publish
        # has on other publishes.

        # get the path in a normalized state. no trailing separator, separators
        # are appropriate for current os, no double separators, etc.

        # Ensure that the destination path exists before exporting since the
        # Unreal FBX exporter doesn't check that
        filename = item.properties["path"]
        self.parent.ensure_folder_exists(os.path.dirname(filename))

        # Export the asset from Unreal
        actor = item.properties["actor"]
        actor_name = item.properties["actor_name"]
        binding = item.properties["binding"]
        if not binding:
            _unreal_export_actor_to_fbx(filename, actor)
        else:
            _unreal_export_anim_actor_to_fbx(filename, actor, binding)

        # let the base class register the publish
        # the publish_file will copy the file from the work path to the publish path
        # if the item is provided with the worK_template and publish_template properties
        super(UnrealActorPublishPlugin, self).publish(settings, item)

    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """
        # do the base class finalization
        try:
            super(UnrealActorPublishPlugin, self).finalize(settings, item)
        except:
            pass  # !FIXME: Raise exception when publish to not assigned task. The field is not editable for this user: [PublishedFile.sg_status_list]


def _unreal_export_anim_actor_to_fbx(filename, actor, binding):
    """
    Export an actor to FBX from Unreal
    """
    # Get an export task
    params = _generate_sequencer_export_fbx_params(filename, actor, binding)
    if not params:
        return False, None

    data = unreal_utils.save_state_and_bake([binding])

    # Do the FBX export
    result = unreal.SequencerTools().export_level_sequence_fbx(params)

    unreal_utils.restore_state_after_bake(data)

    if not result:
        unreal.log_error(f"Failed to export {params.fbx_file_name}")
        return result, None

    return result, params.fbx_file_name


def _generate_sequencer_export_fbx_params(filename, actor, binding):
    # Setup AssetExportTask for non-interactive mode
    params = unreal.SequencerExportFBXParams()

    world = actor.get_world()
    params.world = world
    params.sequence = binding.sequence

    params.bindings = [binding]
    params.fbx_file_name = filename        # the filename to export as

    # Setup export options for the export task
    params.override_options = unreal.FbxExportOption()
    params.override_options.collision = False
    params.override_options.bake_camera_and_light_animation = unreal.MovieSceneBakeType.BAKE_ALL
    params.override_options.bake_actor_animation = unreal.MovieSceneBakeType.BAKE_ALL
    params.override_options.level_of_detail = False
    params.override_options.export_local_time = False
    # These are the default options for the FBX export
    # params.override_options.fbx_export_compatibility = fbx_2013
    # params.override_options.ascii = False
    # params.override_options.force_front_x_axis = False
    # params.override_options.vertex_color = True

    # params.override_options.collision = True
    # params.override_options.welded_vertices = True
    # params.override_options.map_skeletal_motion_to_root = False

    return params


def _unreal_export_actor_to_fbx(filename, actor):
    """
    Export an asset to FBX from Unreal

    :param destination_path: The path where the exported FBX will be placed
    :param actor: The Unreal actor to export to FBX
    """
    # Get an export task
    task = _generate_fbx_export_task(filename, actor)
    if not task:
        return False, None

    # Do the FBX export
    result = unreal.Exporter.run_asset_export_task(task)

    if not result:
        unreal.log_error(f"Failed to export {task.filename}")
        for error_msg in task.errors:
            unreal.log_error(f"{error_msg}")

        return result, None

    return result, task.filename


def _generate_fbx_export_task(filename, actor):

    # filename = os.path.join(destination_path, actor_name + ".fbx")

    # Setup AssetExportTask for non-interactive mode
    task = unreal.AssetExportTask()
    task.object = actor.get_world()      # the asset to export
    task.filename = filename        # the filename to export as
    task.automated = False           # don't display the export options dialog
    task.replace_identical = True   # always overwrite the output

    # Setup export options for the export task
    task.options = unreal.FbxExportOption()
    task.options.bake_camera_and_light_animation = unreal.MovieSceneBakeType.BAKE_ALL
    task.options.bake_actor_animation = unreal.MovieSceneBakeType.BAKE_ALL
    task.options.collision = False
    task.options.level_of_detail = False
    # These are the default options for the FBX export
    # task.options.fbx_export_compatibility = fbx_2013
    # task.options.ascii = False
    # task.options.force_front_x_axis = False
    # task.options.vertex_color = True
    # task.options.level_of_detail = True
    # task.options.welded_vertices = True
    # task.options.map_skeletal_motion_to_root = False

    return task
