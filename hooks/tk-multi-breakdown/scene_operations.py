# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import sys

import sgtk
from sgtk import Hook

import unreal

from pathlib import Path
libs_path = os.path.join(str(Path(__file__).parents[2]), 'libs')
sys.path.insert(0, libs_path)
import unreal_utils


class BreakdownSceneOperations(Hook):
    """
    Breakdown operations for Unreal.

    The updating part of this implementation relies on the importing
    functionnalities of the tk-multi-loader2.unreal's Hook.
    """

    def scan_scene(self):
        """
        The scan scene method is executed once at startup and its purpose is
        to analyze the current scene and return a list of references that are
        to be potentially operated on.

        The return data structure is a list of dictionaries. Each scene reference
        that is returned should be represented by a dictionary with three keys:

        - "node": The name of the 'node' that is to be operated on. Most DCCs have
          a concept of a node, path or some other way to address a particular
          object in the scene.
        - "type": The object type that this is. This is later passed to the
          update method so that it knows how to handle the object.
        - "path": Path on disk to the referenced object.

        Toolkit will scan the list of items, see if any of the objects matches
        any templates and try to determine if there is a more recent version
        available. Any such versions are then displayed in the UI as out of date.
        """
        refs = []
        # Parse Unreal Editor Assets
        # Call _build_scene_item_dict method on each asset to build the scene_item_dict (node, type, path)
        # The _build_scene_item_dict method can be overriden by derived hooks.
        cur_level = unreal.LevelEditorSubsystem().get_current_level().get_path_name()
        path, _ = os.path.split(cur_level)
        unreal.log(f"Current Level: {path}")
        splitted = path.split("/")[:5]
        path = "/".join(splitted)
        unreal.log(f"Current SHOT: {path}")

        for asset_path in unreal.EditorAssetLibrary.list_assets(path):
            unreal.log(f"Found asset: {asset_path}")
            scene_item_dict = self._build_scene_item_dict(asset_path)
            if not scene_item_dict:
                continue
            unreal.log(f"Accept item: {scene_item_dict}")
            refs.append(scene_item_dict)

        return refs

    def _build_scene_item_dict(self, asset_path: str):
        """
        If the UAsset at `asset_path` has the tag `SOURCE_PATH_TAG` defined in
        `tk-framework-imgspc`, build the scene item dict that will be used
        by the `tk-multi-breakdown` app to determine if there is a more recent
        version available.

        If the studio's workflow is not compatible with the use of tags, this
        method should be overriden in derived Hooks to provide its own logic.

        :param asset_path: Path of the UAsset to check
        :returns: scene item dict or None
        """

        # engine = sgtk.platform.current_engine()
        asset_data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
        asset_type = asset_data.get_class().get_name()
        # unreal.log(f"Asset type: {asset_type}")
        if asset_type not in ('GeometryCache', 'AnimSequence', 'StaticMesh', 'SkeletalMesh', 'Skeleton'):
            return

        asset = unreal.load_asset(asset_path)
        if not asset:
            return

        try:
            source_path = asset.get_editor_property("asset_import_data").get_first_filename()
        except:
            unreal.log_error(f"Can't get source file from asset: ", asset_path)
            return

        # sgtk_path = unreal.EditorAssetLibrary.get_metadata_tag(asset, "SG.url")
        # if not sgtk_path:
        #     self.logger.debug("Asset `{}` does not have the tag `{}`".format(
        #         asset.get_path_name(), source_path
        #     ))
        #     return None

        scene_item_dict = {
            "node": asset.get_path_name(),
            "node_name": asset.get_path_name(),
            "type": str(type(asset)),
            "node_type": str(type(asset)),
            # Must be a path linked ot a template with a {version} key
            # (see tk-multi-breakdown/python/tk_multi_breakdown/breakdown.py)
            "path": source_path,
        }

        return scene_item_dict

    def update(self, item=None, items=None):
        """
        Perform replacements given a number of scene items passed from the app.

        The method relies on `tk-multi-loader2.unreal` `action_mappings` hook:
        the update is an import replacing the older version. This way, this
        `update` method can update all the types the loader can load, and will
        also apply the same metadata.

        Once a selection has been performed in the main UI and the user clicks
        the update button, this method is called.

        The items parameter is a list of dictionaries on the same form as was
        generated by the scan_scene hook above. The path key now holds
        the that each node should be updated *to* rather than the current path.
        """

        def item_update(item):
            node_path = item.get("node", item["node_name"])
            node_type = item.get("type", item["node_type"])
            file_path = item["path"]

            asset_to_update = unreal.load_asset(node_path)
            if not asset_to_update:
                unreal.log(f"Could not load asset {asset_to_update}.")
                return

            asset_path = unreal.Paths.get_path(asset_to_update.get_path_name())
            asset_name = asset_to_update.get_name()
            new_source_file_path = file_path

            publishes = sgtk.util.find_publish(
                self.sgtk,
                [new_source_file_path],
                fields=[
                    "name",
                    "path",
                    "task",
                    "entity",
                    "created_by",
                    "version_number",
                    "published_file_type",
                ]
            )
            sg_publish_data = publishes.get(new_source_file_path)
            if not sg_publish_data:
                unreal.log_warning(
                    f"No PublishedFile found in Shotgun for path `{new_source_file_path}`"
                )
                return

            try:
                published_file_type = sg_publish_data["published_file_type"]["name"]
            except:
                return

            unreal.log(
                f"Try to update {node_path}/{asset_name} with {published_file_type} '{new_source_file_path}'"
            )
            if published_file_type == "FBX":
                unreal_utils.unreal_import_fbx_asset(new_source_file_path, asset_path, asset_name)
            elif published_file_type == "FBX Camera":
                unreal_utils.unreal_import_fbx_camera(new_source_file_path, asset_path, asset_name)
            elif published_file_type == "Alembic Cache":
                unreal_utils.unreal_import_alembic_asset(new_source_file_path, asset_path, asset_name)
            elif published_file_type == "Alembic Camera":
                unreal_utils.unreal_import_alembic_camera(new_source_file_path, asset_path, asset_name)

        if items:
            for item in items:
                item_update(item)
        else:
            item_update(item)
