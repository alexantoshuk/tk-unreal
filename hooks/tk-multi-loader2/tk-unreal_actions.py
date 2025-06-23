# This file is based on templates provided and copyrighted by Autodesk, Inc.
# This file has been modified by Epic Games, Inc. and is subject to the license
# file included in this repository.

"""
Hook that loads defines all the available actions, broken down by publish type.
"""

import os
import sys
import sgtk
import unreal
import re

HookBaseClass = sgtk.get_hook_baseclass()

from pathlib import Path
libs_path = os.path.join(str(Path(__file__).parents[2]), 'libs')
sys.path.insert(0, libs_path)
import unreal_utils


class UnrealActions(HookBaseClass):

    ##############################################################################################################
    # public interface - to be overridden by deriving classes

    def generate_actions(self, sg_publish_data, actions, ui_area):
        """
        Returns a list of action instances for a particular publish.
        This method is called each time a user clicks a publish somewhere in the UI.
        The data returned from this hook will be used to populate the actions menu for a publish.

        The mapping between Publish types and actions are kept in a different place
        (in the configuration) so at the point when this hook is called, the loader app
        has already established *which* actions are appropriate for this object.

        The hook should return at least one action for each item passed in via the
        actions parameter.

        This method needs to return detailed data for those actions, in the form of a list
        of dictionaries, each with name, params, caption and description keys.

        Because you are operating on a particular publish, you may tailor the output
        (caption, tooltip etc) to contain custom information suitable for this publish.

        The ui_area parameter is a string and indicates where the publish is to be shown.
        - If it will be shown in the main browsing area, "main" is passed.
        - If it will be shown in the details area, "details" is passed.
        - If it will be shown in the history area, "history" is passed.

        Please note that it is perfectly possible to create more than one action "instance" for
        an action! You can for example do scene introspection - if the action passed in
        is "character_attachment" you may for example scan the scene, figure out all the nodes
        where this object can be attached and return a list of action instances:
        "attach to left hand", "attach to right hand" etc. In this case, when more than
        one object is returned for an action, use the params key to pass additional
        data into the run_action hook.

        :param sg_publish_data: Shotgun data dictionary with all the standard publish fields.
        :param actions: List of action strings which have been defined in the app configuration.
        :param ui_area: String denoting the UI Area (see above).
        :returns List of dictionaries, each with keys name, params, caption and description
        """
        app = self.parent
        app.log_debug("Generate actions called for UI element %s. "
                      "Actions: %s. Publish Data: %s" % (ui_area, actions, sg_publish_data))

        action_instances = []

        if "import_fbx_camera" in actions:
            action_instances.append({"name": "import_fbx_camera",
                                     "params": None,
                                     "caption": "Import Camera Actor",
                                     "description": "This will import camera actor with animation track."})
        if "import_fbx" in actions:
            action_instances.append({"name": "import_fbx",
                                     "params": None,
                                     "caption": "Import into Content Browser",
                                     "description": "This will import the asset into the Unreal Editor Content Browser."})
        if "import_alembic" in actions:
            action_instances.append({"name": "import_alembic",
                                     "params": None,
                                     "caption": "Import into Content Browser",
                                     "description": "This will import Alembic cache into the Unreal Editor Content Browser."})
        if "import_vdb" in actions:
            action_instances.append({"name": "import_vdb",
                                     "params": None,
                                     "caption": "Import into Content Browser",
                                     "description": "This will import VDB cache into the Unreal Editor Content Browser."})

        if "import_alembic_camera" in actions:
            action_instances.append({"name": "import_alembic_camera",
                                     "params": None,
                                     "caption": "Import Camera into Content Browser",
                                     "description": "This will import Alembic cache into the Unreal Editor Content Browser."})

        return action_instances

    def execute_multiple_actions(self, actions):
        """
        Executes the specified action on a list of items.

        The default implementation dispatches each item from ``actions`` to
        the ``execute_action`` method.

        The ``actions`` is a list of dictionaries holding all the actions to execute.
        Each entry will have the following values:

            name: Name of the action to execute
            sg_publish_data: Publish information coming from Shotgun
            params: Parameters passed down from the generate_actions hook.

        .. note::
            This is the default entry point for the hook. It reuses the ``execute_action``
            method for backward compatibility with hooks written for the previous
            version of the loader.

        .. note::
            The hook will stop applying the actions on the selection if an error
            is raised midway through.

        :param list actions: Action dictionaries.
        """
        for single_action in actions:
            name = single_action["name"]
            sg_publish_data = single_action["sg_publish_data"]
            params = single_action["params"]
            self.execute_action(name, params, sg_publish_data)

    def execute_action(self, name, params, sg_publish_data):
        """
        Execute a given action. The data sent to this be method will
        represent one of the actions enumerated by the generate_actions method.

        :param name: Action name string representing one of the items returned by generate_actions.
        :param params: Params data, as specified by generate_actions.
        :param sg_publish_data: Shotgun data dictionary with all the standard publish fields.
        :returns: No return value expected.
        """
        app = self.parent
        app.log_debug("Execute action called for action %s. "
                      "Parameters: %s. Publish Data: %s" % (name, params, sg_publish_data))

        # resolve path
        path = self.get_publish_path(sg_publish_data)

        if name in ("import_fbx_camera", "import_fbx", "import_alembic", "import_alembic_camera", "import_vdb"):
            self._import_to_content_browser(path, sg_publish_data, name)
        else:
            try:
                HookBaseClass.execute_action(self, name, params, sg_publish_data)
            except AttributeError:
                # base class doesn't have the method, so ignore and continue
                pass

    def _import_to_content_browser(self, path, sg_publish_data, action_name):
        """
        Import the asset into the Unreal Content Browser.

        :param path: Path to file.
        :param sg_publish_data: Shotgun data dictionary with all the standard publish fields.
        """
        unreal.log("File to import: {}".format(path))
        if not os.path.exists(path):
            raise Exception("File not found on disk - '%s'" % path)

        asset_path = None

        if action_name == "import_fbx":
            destination_path, destination_name = self._get_destination_path_and_name(sg_publish_data)
            asset_path = unreal_utils.unreal_import_fbx_asset(path, destination_path, destination_name, automated=False)

        elif action_name == "import_alembic":
            destination_path, destination_name = self._get_destination_path_and_name(sg_publish_data)
            asset_path = unreal_utils.unreal_import_alembic_asset(path, destination_path, destination_name, create_actor=True)

        elif action_name == "import_vdb":
            destination_path, destination_name = self._get_destination_path_and_name(sg_publish_data)
            asset_path = unreal_utils.unreal_import_vdb(path, destination_path, destination_name, create_actor=True)

        elif action_name == "import_fbx_camera":
            destination_path, destination_name = self._get_destination_camera_path_and_name(sg_publish_data)
            ok = unreal_utils.unreal_import_fbx_camera(path, destination_path, destination_name)

        elif action_name == "import_alembic_camera":
            destination_path, destination_name = self._get_destination_camera_path_and_name(sg_publish_data)
            asset_path = unreal_utils.unreal_import_alembic_camera(path, destination_path, destination_name)

        if asset_path:
            self._set_asset_metadata(asset_path, sg_publish_data)

    def _set_asset_metadata(self, asset_path, sg_publish_data):
        """
        Set needed metadata on the given asset
        """
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)

        if not asset:
            return

        engine = sgtk.platform.current_engine()

        # Add a metadata tag for "created_by"
        if "created_by" in sg_publish_data:
            createdby_dict = sg_publish_data["created_by"]
            name = ""
            if "name" in createdby_dict:
                name = createdby_dict["name"]
            elif "id" in createdby_dict:
                name = createdby_dict["id"]

            tag = engine.get_metadata_tag("created_by")
            unreal.EditorAssetLibrary.set_metadata_tag(asset, tag, name)

        # Add a metadata tag for the Shotgun URL
        # Construct the PublishedFile URL from the publish data type and id since
        # the context of a PublishedFile is the Project context
        shotgun_site = self.sgtk.shotgun_url
        type = sg_publish_data["type"]
        id = sg_publish_data["id"]
        url = shotgun_site + "/detail/" + type + "/" + str(id)

        """
        # Get the URL from the context (Asset, Task, Project)
        # The context of the publish data is usually the Task (or Project if there's no task)
        # But try to be more specific by using the context of the linked entity (Asset)
        entity_dict = sg_publish_data["entity"]
        context = self.sgtk.context_from_entity_dictionary(entity_dict)
        url = context.shotgun_url

        if entity_dict["type"] == "Project":
            # As a last resort, construct the PublishedFile URL from the publish data type and id since
            # the context of a PublishedFile is the Project context
            shotgun_site = self.sgtk.shotgun_url
            type = sg_publish_data["type"]
            id = sg_publish_data["id"]
            url = shotgun_site + "/detail/" + type + "/" + str(id)
        """

        tag = engine.get_metadata_tag("url")
        unreal.EditorAssetLibrary.set_metadata_tag(asset, tag, url)

        unreal.EditorAssetLibrary.save_loaded_asset(asset)

    ##############################################################################################################
    # helper methods which can be subclassed in custom hooks to fine tune the behaviour of things

    def _get_destination_camera_path_and_name(self, sg_publish_data):
        """
        Get the destination path and name from the publish data and the templates

        :param sg_publish_data: Shotgun data dictionary with all the standard publish fields.
        :return destination_path that matches a template and destination_name from asset or published file
        """

        # Get the name field from the Publish Data
        name = sg_publish_data["name"]
        name, ext = os.path.splitext(name)

        # Get the publish context to determine the template to use
        context = self.sgtk.context_from_entity_dictionary(sg_publish_data)

        # Get the destination templates based on the context
        # Assets and Shots supported by default
        # Other entities fall back to Project
        if context.entity["type"] == "Shot":
            destination_template = self.sgtk.templates["unreal_loader_shot_path"]
            destination_name_template = self.sgtk.templates["unreal_loader_shot_name"]
        else:
            raise Exception("Can't determine context for loading camera '{name}'")

        task_id = sg_publish_data['task']['id']
        step_short_name = unreal_utils.step_short_name(task_id)
        # For camera step is always 'LAY'
        step_short_name = 'LAY'

        # Query the fields needed for the destination template from the context
        fields = context.as_template_fields(destination_template)

        # Add the name field from the publish data
        fields["name"] = name
        fields["Step"] = step_short_name
        # Get destination path by applying fields to destination template
        # Fall back to the root level if unsuccessful
        destination_path = destination_template.apply_fields(fields)

        # Query the fields needed for the name template from the context
        name_fields = context.as_template_fields(destination_name_template)

        # Add the name field from the publish data
        name_fields["name"] = name

        # Get destination name by applying fields to the name template
        # Fall back to the filename if unsuccessful
        # try:
        #     destination_name = destination_name_template.apply_fields(name_fields)
        # except Exception:
        #     destination_name = _sanitize_name(sg_publish_data["code"])
        # print("INFO: ", ext.lower(), context.entity["type"], context.entity["name"], context.task["name"])
        return destination_path, _sanitize_name(name)

    def _get_destination_path_and_name(self, sg_publish_data):
        """
        Get the destination path and name from the publish data and the templates

        :param sg_publish_data: Shotgun data dictionary with all the standard publish fields.
        :return destination_path that matches a template and destination_name from asset or published file
        """
        # Enable if needed while in development
        # self.sgtk.reload_templates()

        # Get the publish context to determine the template to use
        context = self.sgtk.context_from_entity_dictionary(sg_publish_data)

        # Get the destination templates based on the context
        # Assets and Shots supported by default
        # Other entities fall back to Project
        if context.entity is None:
            destination_template = self.sgtk.templates["unreal_loader_project_path"]
            destination_name_template = self.sgtk.templates["unreal_loader_project_name"]
        elif context.entity["type"] == "Asset":
            destination_template = self.sgtk.templates["unreal_loader_asset_path"]
            destination_name_template = self.sgtk.templates["unreal_loader_asset_name"]
        elif context.entity["type"] == "Shot":
            destination_template = self.sgtk.templates["unreal_loader_shot_path"]
            destination_name_template = self.sgtk.templates["unreal_loader_shot_name"]
        else:
            destination_template = self.sgtk.templates["unreal_loader_project_path"]
            destination_name_template = self.sgtk.templates["unreal_loader_project_name"]

        # Get the name field from the Publish Data
        name = sg_publish_data["name"]
        splitted_name = name.split(".")
        name = splitted_name[0]
        ext = splitted_name[-1]
        task_id = sg_publish_data['task']['id']

        step_short_name = unreal_utils.step_short_name(task_id)

        # Query the fields needed for the destination template from the context
        fields = context.as_template_fields(destination_template)

        # Add the name field from the publish data
        fields["name"] = name
        fields["Step"] = step_short_name
        # Get destination path by applying fields to destination template
        # Fall back to the root level if unsuccessful
        try:
            destination_path = destination_template.apply_fields(fields)
        except Exception:
            destination_path = "/Game/Assets/"

        # Query the fields needed for the name template from the context
        name_fields = context.as_template_fields(destination_name_template)

        # Add the name field from the publish data
        name_fields["name"] = name

        # Get destination name by applying fields to the name template
        # Fall back to the filename if unsuccessful
        # try:
        #     destination_name = destination_name_template.apply_fields(name_fields)
        # except Exception:
        #     destination_name = _sanitize_name(sg_publish_data["code"])
        # print("INFO: ", ext.lower(), context.entity["type"], context.task["name"])
        if ext.lower() == 'fbx' and context.entity["type"] == "Shot" and context.task["name"] in ('Animation',):
            shotname = context.entity["name"]
            if not name.startswith(shotname):
                name = f"{shotname}_{name}"
        return destination_path, _sanitize_name(name)


"""
Functions to import FBX into Unreal
"""


def _sanitize_name(name):
    # Remove the default Shotgun versioning number if found (of the form '.v001')
    name_no_version = re.sub(r'.v[0-9]{3}', '', name)

    # Replace any remaining '.' with '_' since they are not allowed in Unreal asset names
    return name_no_version.replace('.', '_')
