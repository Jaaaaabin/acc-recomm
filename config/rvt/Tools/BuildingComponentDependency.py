# -*- coding: utf-8 -*-
# # IMPORT - BASIC PACKAGES 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================

import clr
from collections import Counter, defaultdict
clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
import os
import System
import Autodesk
from System.Collections.Generic import *
from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory, Structure, ElementId, Phase, SpatialElementBoundaryOptions

# =====================================================================================================
# IMPORT - REVIT Batch UTILITIES
import revit_script_util
from revit_script_util import Output

# =====================================================================================================
# IMPORT - CUSTOM FUNCTIONS.
from Tools.BuildingComponent import SlabComponent, RoomComponent, WallComponent, DoorComponent, WindowComponent
from Tools.BuildingComponent import StructuralColumnComponent, StairComponent, SeparationLineComponent
from Tools.GeometryHelper import get_XYZpoint_as_list, are_lines_parallel_with_distance, is_point_near_line, are_points_aligned, get_combinations
from Tools.GeneralSettings import write_json_data, extract_instance_attributes

# =====================================================================================================
# CLASS - ComponentDependency (Base Class)
class ComponentDependencyConstructor:
    """
    Base class for constructing dependencies between Revit elements.
    """
    def __init__(self):

        self.relationship_type = '' # type name of the relationship, which is set to '' by default.

    def _set_relation_type(self, type_name=''):

        self.relationship_type = type_name

    def _get_phase_by_name(self, doc, target_phase_name="New Construction"):
        """
        Retrieves a Phase element by name from the given document.
        Falls back to the first available phase if not found.
        """
        phases = list(FilteredElementCollector(doc).OfClass(Phase).ToElements())

        # Print all available phases
        for p in phases:
            msg = "phases: Name = {0}, Id = {1}".format(p.Name, p.Id)
            Output(msg)

        # Try to match by name
        selected_phase = None
        for p in phases:
            if p.Name == target_phase_name:
                selected_phase = p
                break

        # Fallback handling
        if not selected_phase and phases:
            selected_phase = phases[0]
            Output("Phase '{0}' not found. Defaulted to first phase: {1}".format(target_phase_name, selected_phase.Name))
        elif selected_phase:
            Output("Selected phase: {0}".format(selected_phase.Name))
        else:
            Output("No phases found in the document.")

        return selected_phase

    def _set_relation_settings(self, doc):

        self.doc = doc
        # self.phase = list(FilteredElementCollector(self.doc).OfClass(Phase).ToElements())[0]
        self.phase = self._get_phase_by_name(self.doc, "New Construction")

        self.element_mapping_ost2string = {
            BuiltInCategory.OST_Rooms: 'space',
            BuiltInCategory.OST_Floors: 'slab',
            BuiltInCategory.OST_Walls: 'wall',
            BuiltInCategory.OST_Doors: 'door',
            BuiltInCategory.OST_Windows: 'window',
            BuiltInCategory.OST_StructuralColumns: 'column',
            BuiltInCategory.OST_Stairs: 'stair',
            BuiltInCategory.OST_RoomSeparationLines: 'separationline'
            }
        
        self.element_mapping_string2ost = {v: k for k, v in self.element_mapping_ost2string.items()}

    def set_common_category_scopes(self, *categories):
        """
        Defines the commonly invovled building element categories as relationship scopes.
        This serves a basic or broad scope for this type of relatioship.
        """

        self.relationship_scopes = set(categories)
        self.collection_all_elements = {}
        self.collection_all_element_pairs = {}
        self.collection_all_component_relationships = {}

        for cat in self.relationship_scopes:
            if cat in self.element_mapping_ost2string:
                cat_elements = list(FilteredElementCollector(self.doc).OfCategory(cat).WhereElementIsNotElementType().ToElements())
                self.collection_all_elements[cat] = cat_elements
            else:
                print("No wrapper defined for:", cat)
        
        category_list = list(self.relationship_scopes)
        for i in range(len(category_list)):
            for j in range(len(category_list)):
                cat_a = category_list[i]
                cat_b = category_list[j]

                if cat_a in self.element_mapping_ost2string and cat_b in self.element_mapping_ost2string:
                    key_name_a = self.element_mapping_ost2string[cat_a]
                    key_name_b = self.element_mapping_ost2string[cat_b]
                    pair_key = key_name_a + "-" + key_name_b
                    self.collection_all_element_pairs[pair_key] = (
                        self.collection_all_elements[cat_a], 
                        self.collection_all_elements[cat_b])
                else:
                    print("Missing name mapping for one or both categories:", cat_a, cat_b)
        
        self.collection_all_component_relationships = {
            key: [] for key in self.collection_all_element_pairs
        }
    
    def _is_a_structural_element(self, element):
        """
        Determines whether a given element is structural.
        # Structure.StructuralWallUsage.NonBearing 0
        # Structure.StructuralWallUsage.Bearing 1
        # Structure.StructuralWallUsage.Shear 2
        # Structure.StructuralWallUsage.Combined 3
        """

        category_id = element.Category.Id.IntegerValue if element.Category else None

        # OST_StructuralColumns: true.
        if category_id == int(BuiltInCategory.OST_StructuralColumns):
            return True
        
        # OST_Walls: based on StructuralUsage.
        if category_id == int(BuiltInCategory.OST_Walls):
            if element.StructuralUsage != Structure.StructuralWallUsage.NonBearing:
                return True
            else:
                return False
        
        # All other types: false.
        return False

    def _clean_repeating_non_directed_pairs(self, key_for_nested_list):

        """
        For each sublist of string IDs:
        - Converts strings to integers,
        - Sorts them,
        - Converts them back to strings.
        Then deduplicates the full list of sublists.
        """
        
        nested_list =  self.collection_all_component_relationships[key_for_nested_list]

        if not nested_list:
            return []

        processed = []
        for sublist in nested_list:
            if not sublist:
                continue
            # Convert to int, sort, back to str
            normalized = [str(x) for x in sorted(int(i) for i in sublist)]
            processed.append(normalized)

        # Deduplicate by converting each to a tuple, then back to list
        unique_processed = list(map(list, set(tuple(x) for x in processed)))
        
        # # Save: print for instant debugging.
        # if len(unique_processed) < len(processed):
        #         print("Removed repeated entries for '{}': {} -> {}".format(
        #             key_for_nested_list, len(processed), len(unique_processed)
        #         ))

        self.collection_all_component_relationships[key_for_nested_list] = unique_processed
    
    def _print_dictionary_by_attribute(self, attribute_name):
        """
        Prints the contents of a dictionary-type attribute by its name.
        """
        if not hasattr(self, attribute_name):
            print("Attribute not found:", attribute_name)
            return

        attr_value = getattr(self, attribute_name)
        if not isinstance(attr_value, dict):
            print("Attribute is not a dictionary:", attribute_name)
            return

        print("\n--------------------- Printing Dictionary:", attribute_name, "---------------------")
        for key, value in attr_value.items(): 
            if value:
                print("Key:", key)
                print("Value:", value)
                print("----------------------------------------------------------------------------------")
    
    def _get_overall_geo_values(self):
        """
        Get basic geometric information serving as tolerance values.
        #  max_slab_thickness: Maximum value of the slab thickness
        #  max_slab_thickness: Maximum value of the slab thickness
        #  max_slab_thickness: Maximum value of the slab thickness
        """
        
        self.max_slab_thickness = 0.0
        self.max_wall_thickness = 0.0
        self.max_column_thickness = 0.0

        for slab in FilteredElementCollector(self.doc).OfCategory(BuiltInCategory.OST_Floors).WhereElementIsNotElementType():
            bbx = slab.get_BoundingBox(None)
            if bbx:
                self.max_slab_thickness = max(self.max_slab_thickness, bbx.Max.Z - bbx.Min.Z)
        
        for wall in FilteredElementCollector(self.doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType():
            if hasattr(wall, "Width"):
                self.max_wall_thickness = max(self.max_wall_thickness, wall.Width)
        
        for col in FilteredElementCollector(self.doc).OfCategory(BuiltInCategory.OST_StructuralColumns).WhereElementIsNotElementType():
                bbx = col.get_BoundingBox(None)
                if bbx:
                    dx = bbx.Max.X - bbx.Min.X
                    dy = bbx.Max.Y - bbx.Min.Y
                    dz = bbx.Max.Z - bbx.Min.Z
                    thickness = min(dx, dy, dz)
                    self.max_column_thickness = max(self.max_column_thickness, thickness)
           
    def _add_relationship(self, k_pair, constructed_relationships):
        if k_pair in self.collection_all_component_relationships:
            self.collection_all_component_relationships[k_pair].extend(constructed_relationships)
        else:
            self.collection_all_component_relationships.update({k_pair: constructed_relationships})
             
    def _match_via_level_id(self, pair_of_elements):
        
        elements_a, elements_b = pair_of_elements
        relationships = []
        for element_a in elements_a:
            level_id_a = element_a.LevelId
            if level_id_a == ElementId.InvalidElementId:
                continue

            for element_b in elements_b:

                #---------skip conditions: no calculation for the same element.---------
                if element_a.Id == element_b.Id:
                    continue
                
                level_id_b = element_b.LevelId
                if level_id_b == ElementId.InvalidElementId:
                    continue

                if level_id_a == level_id_b:
                    relationships.append((str(element_a.Id), str(element_b.Id)))

        return relationships
    
    def _match_via_advanced_opening_host(
        self,
        pair_of_elements,
        ):

        _, elements_b = pair_of_elements
        relationships = []

        # Query the hostID from element_b, which is either a door or a window.
        for element_b in elements_b:        
            if element_b.Host:
                relationships.append((str(element_b.Host.Id), str(element_b.Id)))
            else:
                continue

        return relationships

    def _match_via_pair_bbx(
        self,
        pair_of_elements,
        match_mode=None,
        match_level="all", 
        reshape_x_y_z=[0.0,0.0,0.0],
        factor_inclusion=1.0,
    ):
        """
        Detects bounding box overlaps with optional extension in x, y and z directions (tolerance).
        """
        elements_a, elements_b = pair_of_elements
        relationships = []

        for element_a in elements_a:
        
            # increased reshape: [+, +, +], or descreased reshape:[-, -, -]
            bbx_a = element_a.get_BoundingBox(None)
            min_a_xyz = (bbx_a.Min.X - reshape_x_y_z[0], bbx_a.Min.Y - reshape_x_y_z[1], bbx_a.Min.Z - reshape_x_y_z[2])
            max_a_xyz = (bbx_a.Max.X + reshape_x_y_z[0], bbx_a.Max.Y + reshape_x_y_z[1], bbx_a.Max.Z + reshape_x_y_z[2])
            
        
            for element_b in elements_b:

                if "all" not in match_level:
                    # only if the match_level is enbaled, we extract the level id. 
                    level_id_a, level_id_b = element_a.LevelId, element_b.LevelId
                    if  ("same" in match_level and level_id_a != level_id_b) or ("different" in match_level and level_id_a == level_id_b):
                        continue
    
                # skip if they're actually the same building component.
                if element_a.Id == element_b.Id:
                    continue
                 
                # increased reshape: [+, +, +], or descreased reshape:[-, -, -]
                bbx_b = element_b.get_BoundingBox(None)
                bbx_b_volume_xyz = (bbx_b.Max.X - bbx_b.Min.X) * (bbx_b.Max.Y - bbx_b.Min.Y) * (bbx_b.Max.Z - bbx_b.Min.Z)
                min_b_xyz = (bbx_b.Min.X - reshape_x_y_z[0], bbx_b.Min.Y - reshape_x_y_z[1], bbx_b.Min.Z - reshape_x_y_z[2])
                max_b_xyz = (bbx_b.Max.X + reshape_x_y_z[0], bbx_b.Max.Y + reshape_x_y_z[1], bbx_b.Max.Z + reshape_x_y_z[2])

                x_overlap = max(0, min(max_a_xyz[0], max_b_xyz[0]) - max(min_a_xyz[0], min_b_xyz[0]))
                y_overlap = max(0, min(max_a_xyz[1], max_b_xyz[1]) - max(min_a_xyz[1], min_b_xyz[1]))
                z_overlap = max(0, min(max_a_xyz[2], max_b_xyz[2]) - max(min_a_xyz[2], min_b_xyz[2]))
                
                xy_overlap_area = x_overlap * y_overlap
                xyz_overlap_volume = xy_overlap_area * z_overlap
                
                is_match = False

                # default is by intersection.
                if "intersection" in match_mode:
                    # just intersection
                    is_match = xyz_overlap_volume > 0

                elif "inclusion" in match_mode:
                    # full containment
                    is_match = xyz_overlap_volume >= bbx_b_volume_xyz * factor_inclusion

                else:
                    print("no correct mode selected.")

                if is_match:
                    relationships.append((str(element_a.Id), str(element_b.Id)))

        return relationships

    def _match_via_advanced_wall_dependency(self, pair_of_elements):
        
        elements_a, elements_b = pair_of_elements
        relationships = []
        
        room_boundary_wall_ids = set(elem.Id for elem in elements_b)

        for room in elements_a:
            if not room or not room.Location:
                continue

            try:
                segments = room.GetBoundarySegments(SpatialElementBoundaryOptions())
            except:
                continue  # In case of broken geometry
                        
            for seg_list in segments:
                for seg in seg_list: # stored in a list..
                    pair = (str(room.Id), str(seg.ElementId))
                    if seg.ElementId in room_boundary_wall_ids and pair not in relationships:
                        # TODO: needs revision...
                        relationships.append(pair)
                    else:
                        continue
                
        return relationships
    
    def _match_accessibility_via_door(self, pair_of_elements):
        """
        Matches Room  Door using FromRoom and ToRoom info, based on a given Phase.
        """
        
        elements_a, elements_b = pair_of_elements
        relationships = []

        def get_room_ids_of_door(door):
            from_room = door.get_FromRoom(self.phase)
            to_room = door.get_ToRoom(self.phase)
            return (from_room.Id if from_room else None, to_room.Id if to_room else None)

        for room in elements_a:
            room_id = room.Id
            for door in elements_b:
                from_id, to_id = get_room_ids_of_door(door)
                if from_id == room_id or to_id == room_id:
                    pair = (str(room_id), str(door.Id))
                    if pair not in relationships:
                        relationships.append(pair)

        return relationships

    def _match_accessibility_via_separationline(self, pair_of_elements):
        
        elements_a, elements_b = pair_of_elements
        relationships = []
        
        room_boundary_wall_ids = set(elem.Id for elem in elements_b)

        for room in elements_a:
            if not room or not room.Location:
                continue

            try:
                segments = room.GetBoundarySegments(SpatialElementBoundaryOptions())
            except Exception as e:
                print("[ERROR] Unexpected error while getting boundary segments for room {}".format(room.Id))
                continue

            for seg_list in segments:
                for seg in seg_list: # stored in a list..
                    pair = (str(room.Id), str(seg.ElementId))
                    if seg.ElementId in room_boundary_wall_ids and pair not in relationships:
                        relationships.append(pair)
                    else:
                        continue

        return relationships

    def _match_alignment_line_line(
        self,
        pair_of_elements,
        t_alignment,
        match_mode=None,
        match_level="all",
        ):

        elements_a, elements_b = pair_of_elements
        relationships = []

        for element_a in elements_a:
        
            element_line_loc_a = element_a.Location

            for element_b in elements_b:
                element_line_loc_b = element_b.Location

                if "all" not in match_level:
                    # only if z match_level is enbaled, we extract the level id. 
                    level_id_a, level_id_b = element_a.LevelId, element_b.LevelId
                    if  ("same" in match_level and level_id_a != level_id_b) or ("different" in match_level and level_id_a == level_id_b):
                        continue

                if element_a.Id == element_b.Id:
                    continue
                
                # process the revit wall locations (LocationCurve)
                element_line_loc_a_points = [
                    get_XYZpoint_as_list(element_line_loc_a.Curve.GetEndPoint(0)),
                    get_XYZpoint_as_list(element_line_loc_a.Curve.GetEndPoint(1))]
                element_line_loc_b_points = [
                    get_XYZpoint_as_list(element_line_loc_b.Curve.GetEndPoint(0)),
                    get_XYZpoint_as_list(element_line_loc_b.Curve.GetEndPoint(1))]
                
                # calculate 'are_lines_parallel_with_distance'
                is_parallel, parallel_dist = are_lines_parallel_with_distance(
                    element_line_loc_a_points, element_line_loc_b_points)
                
                if is_parallel:
                    
                    # parallel
                    if parallel_dist <= t_alignment:
                        relationships.append((str(element_a.Id), str(element_b.Id)))
                    else:
                        continue
                else:
                    
                    # not parallel
                    continue

        return relationships
    
    def _match_alignment_line_point(
        self,
        pair_of_elements,
        t_alignment,
        match_mode=None,
        match_level="all",
        ):

        elements_a, elements_b = pair_of_elements
        relationships = []

        for element_a in elements_a:
        
            element_line_loc_a = element_a.Location
        
            for element_b in elements_b:
                element_point_loc_b = element_b.Location
                
                # In Revit, the Z coordinate of a column's location point is typically set to zero
                # because it represents the elevation relative to the project's base level or reference level.
                # A value of zero means that the column is placed at the same elevation as the base level or reference level.

                if "all" not in match_level:
                    # only if z match_level is enbaled, we extract the level id. 
                    level_id_a, level_id_b = element_a.LevelId, element_b.LevelId
                    if  ("same" in match_level and level_id_a != level_id_b) or ("different" in match_level and level_id_a == level_id_b):
                        continue

                if element_a.Id == element_b.Id:
                    continue

                # process the revit wall locations (LocationCurve) and column location points
                element_line_loc_a_points = [
                    get_XYZpoint_as_list(element_line_loc_a.Curve.GetEndPoint(0)),
                    get_XYZpoint_as_list(element_line_loc_a.Curve.GetEndPoint(1))]
                element_point_loc_b_singlepoint = get_XYZpoint_as_list(element_point_loc_b.Point)
                
                # prepocessing for Column location (the Z location) 
                # In Revit, the Z coordinate of a column's location point is typically set to zero
                # because it represents the elevation relative to the project's base level or reference level.
                element_point_loc_b_singlepoint[2] += self.doc.GetElement(element_b.LevelId).Elevation

                # calculate 'is_point_near_line'
                # TODO: leverage the returned results 'is_within_segment'.
                is_within_segment, point_line_dist = is_point_near_line(element_line_loc_a_points, element_point_loc_b_singlepoint)

                if point_line_dist <= t_alignment:
                    relationships.append((str(element_a.Id), str(element_b.Id)))
                else:
                    continue

        return relationships
    
    # def _match_alignment_group_of_points(
    #     self,
    #     pair_of_elements,
    #     t_alignment,
    #     ):

    #     all_elements, _ = pair_of_elements
    #     relationships = []
        
    #     # predivide the elements into subgroups.
    #     all_elements_by_level_groups = {}
    #     for elem in all_elements:
    #         level_id = str(elem.LevelId)
    #         if level_id not in all_elements_by_level_groups:
    #             all_elements_by_level_groups[level_id] = []
    #         all_elements_by_level_groups[level_id].append(elem)
        
    #     for k, v in all_elements_by_level_groups.items():
    #         print (k, len(v))

    #     for list_of_elements in all_elements_by_level_groups.values():

    #         element_groups_of_given_size = get_combinations(list_of_elements, t_alignment) # this step might take a lot of time.
            
    #         for elem_group in element_groups_of_given_size:
                
    #             # all from the same level (no need to incorporate the level elevation since it's all with Z=0.0)
    #             # level_z = self.doc.GetElement(elem_group[0].LevelId).Elevation
    #             group_elements_location = [elem.Location for elem in elem_group]
    #             group_elements_location_points = [get_XYZpoint_as_list(elem_loc.Point) for elem_loc in group_elements_location]
            
    #             all_points_aligned = are_points_aligned(group_elements_location_points)
                
    #             if all_points_aligned:
    #                 relationships.append([str(elem.Id) for elem in elem_group])
    #             else:
    #                 continue

    #     return relationships
    
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - AccessibleConnectivityDependency (Subclass)
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class AccessibleConnectivityDependency(ComponentDependencyConstructor):
    """
    Dentifies accessibility relationships.
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    (a) Accessible Connectivity
    horizontal (1 types):       space-door
    ------------------------------------------------------------------------------------------
    vertical (2 types):         space-stair, stair-stair
    Additional one:             space-separationline
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    """

    def __init__(self, doc, type_name, dependency_matix=dict()):
        self.collection_all_elements = {}
        self.collection_all_element_pairs = {}
        self.collection_all_component_relationships = {}
        self.dependency_matix = dependency_matix if dependency_matix else defaultdict()

        self._set_relation_type(type_name)
        self._set_relation_settings(doc)
        self._get_overall_geo_values()

    def construct_relationships(self):
        
        for k_pair, v_pair_basis in self.dependency_matix.items():

            processing_element_pairs = self.collection_all_element_pairs[k_pair]

            if v_pair_basis == "door-to-from":
                # space-door
                constructed_relationship = self._match_accessibility_via_door(
                    pair_of_elements=processing_element_pairs)
                self.collection_all_component_relationships[k_pair] = constructed_relationship
            
            elif v_pair_basis == "space-boundary":
                # space-separationline
                constructed_relationship = self._match_accessibility_via_separationline(
                    pair_of_elements=processing_element_pairs)
                self.collection_all_component_relationships[k_pair] = constructed_relationship
                
            elif "bbx" in v_pair_basis and "stair" in k_pair:
                # stair-stair, space-stair
                constructed_relationship = self._match_via_pair_bbx(
                    pair_of_elements=processing_element_pairs,
                    match_mode=v_pair_basis,
                    reshape_x_y_z=[0.0, 0.0, self.max_slab_thickness*0.5]) # 0.5 might needs to be tuned.

            else:
                print("There's another case which is superisingly not included.")
                continue
            
            self._add_relationship(k_pair,constructed_relationship)

        self._clean_repeating_non_directed_pairs("stair-stair")
    
        # self._build_accessibility_between_rooms()
        # self._build_door_accessibility_with_one_room()

        # self._print_dictionary_by_attribute('collection_all_component_relationships')
    
    def _build_accessibility_between_rooms(self):
        """
        Optimized generation of:
        - 'room-door-room' (via door)
        - 'room-separationline-room' (via separation line)
        """
        result_triplets = {
            "room-door-room": [],
            "room-separationline-room": []
        }

        # Sets to track uniqueness
        seen_door_triplets = set()
        seen_sep_triplets = set()

        # === room-door-room ===
        room_door_pairs = self.collection_all_component_relationships.get("room-door", [])
        door_map = {}
        for room_id, door_id in room_door_pairs:
            door_map.setdefault(door_id, []).append(room_id)

        for door_id, rooms in door_map.items():
            if len(rooms) == 2:
                r1, r2 = sorted(rooms)
                key = (r1, door_id, r2)
                if key not in seen_door_triplets:
                    result_triplets["room-door-room"].append([r1, door_id, r2])
                    seen_door_triplets.add(key)

        # === room-separationline-room ===
        room_sep_pairs = self.collection_all_component_relationships.get("room-separationline", [])
        sep_map = {}
        for room_id, sep_id in room_sep_pairs:
            sep_map.setdefault(sep_id, []).append(room_id)

        for sep_id, rooms in sep_map.items():
            if len(rooms) == 2:
                r1, r2 = sorted(rooms)
                key = (r1, sep_id, r2)
                if key not in seen_sep_triplets:
                    result_triplets["room-separationline-room"].append([r1, sep_id, r2])
                    seen_sep_triplets.add(key)

        self.collection_all_component_relationships.update(result_triplets)
    
    def _build_door_accessibility_with_one_room(self):
        """
        Identifies doors that are only associated with a single room, and classifies them as:
        - 'door_within_room': if both FromRoom and ToRoom point to the same room
        - 'door_to_buildingexit': if one of FromRoom or ToRoom is None
        """
        
        self.collection_all_component_relationships["door_within_room"] = []
        self.collection_all_component_relationships["door_to_buildingexit"] = []

        room_door_pairs = self.collection_all_component_relationships.get("room-door", [])
        door_counts = Counter(door_id for _, door_id in room_door_pairs)
        
        # Filter those that appear only once
        ids_door_with_one_room = [door_id for _, door_id in room_door_pairs if door_counts[door_id] == 1]
        for door_id in ids_door_with_one_room:

            door_element = self.doc.GetElement(ElementId(int(door_id)))
            from_room = door_element.get_FromRoom(self.phase)
            to_room = door_element.get_ToRoom(self.phase)

            if from_room and to_room and from_room.Id == to_room.Id:
                self.collection_all_component_relationships["door_within_room"].append(str(door_id))
            elif from_room is None or to_room is None:
                self.collection_all_component_relationships["door_to_buildingexit"].append(str(door_id))

# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - AdjacentConnectivityDependency (Subclass)
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class AdjacentConnectivityDependency(ComponentDependencyConstructor):
    """
    Identifies spatial intersection relationships.
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    (b) Adjacent Connectivity
    In total (8 types):         slab-space, slab-wall, slab-column, slab-stair, stair-stair, wall-wall, space-wall
    Completed:                  slab-space, slab-wall, slab-column
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    """
    def __init__(self, doc, type_name, dependency_matix=dict()):
        
        self.collection_all_elements = {} # all the building elements, classified via a dictionary by element categories.
        self.collection_all_element_pairs = {} # all the paris of the building elements, classified via a dictionary by element (category key) pairs. 
        self.collection_all_component_relationships = {} # all building element relationships, classified via a dictionary by element (category key) pairs.
        self.dependency_matix = dependency_matix if dependency_matix else defaultdict()

        self._set_relation_type(type_name)
        self._set_relation_settings(doc)
        self._get_overall_geo_values()

    def construct_relationships(self):
       
        for k_pair, v_pair_basis in self.dependency_matix.items():

            processing_element_pairs = self.collection_all_element_pairs[k_pair]
            
            if v_pair_basis == "slab-level":
                # slab-space, slab-wall, slab-column
                constructed_relationship = self._match_via_level_id(processing_element_pairs)
            
            elif v_pair_basis == "bbx-intersection" and k_pair =="wall-stair":
                # wall-stair
                extension_hori = self.max_wall_thickness
                reduction_verti = self.max_slab_thickness
                constructed_relationship = self._match_via_pair_bbx(
                        pair_of_elements=processing_element_pairs,
                        match_mode=v_pair_basis,
                        reshape_x_y_z=[extension_hori, extension_hori, -reduction_verti*0.5],) # reduction weights might needs to be tuned.
            
            elif v_pair_basis == "bbx-intersection" and "stair" not in k_pair: 
                # wall-wall
                constructed_relationship = self._match_via_pair_bbx(
                    pair_of_elements=processing_element_pairs,
                    match_mode=v_pair_basis,
                    reshape_x_y_z=[0.0, 0.0, 0.0])
            
            elif v_pair_basis == "bbx-intersection" and "stair" in k_pair:
                # stair-stair, slab-stair
                constructed_relationship = self._match_via_pair_bbx(
                    pair_of_elements=processing_element_pairs,
                    match_mode=v_pair_basis,
                    reshape_x_y_z=[0.0, 0.0, self.max_slab_thickness*0.5]) # 0.5 might needs to be tuned.
            
            elif v_pair_basis == "space-boundary" :
                # space-wall
                constructed_relationship = self._match_via_advanced_wall_dependency(processing_element_pairs)
            
            else:
                print("There's another case which is superisingly not included.")
                continue

            self._add_relationship(k_pair,constructed_relationship)
        
        self._clean_repeating_non_directed_pairs("stair-stair")
        self._clean_repeating_non_directed_pairs("wall-wall")
        # self._print_dictionary_by_attribute('collection_all_component_relationships')
    
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - SpatialContainmentDependency (Subclass)
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class SpatialContainmentDependency(ComponentDependencyConstructor):
    """
    Identifies spatial containment relationships.
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    (c) Spatial Containment
    In total (5 types):         space-column, space-stair, space-wall, wall-window, wall-door. 
    Completed:                  wall-window, wall-door, space-wall.
    ToCheck:                    space-column, space-stair.
                                check the intersection overlap percent.
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    """

    def __init__(self, doc, type_name, dependency_matix=dict()):
        
        self.collection_all_elements = {} # all the building elements, classified via a dictionary by element categories.
        self.collection_all_element_pairs = {} # all the paris of the building elements, classified via a dictionary by element (category key) pairs. 
        self.collection_all_component_relationships = {} # all building element relationships, classified via a dictionary by element (category key) pairs.
        self.dependency_matix = dependency_matix if dependency_matix else defaultdict()

        self._set_relation_type(type_name)
        self._set_relation_settings(doc)
        self._get_overall_geo_values()

    def construct_relationships(self):

        for k_pair, v_pair_basis in self.dependency_matix.items():

            processing_element_pairs = self.collection_all_element_pairs[k_pair]

            if v_pair_basis == "wall-opening":
                # wall-window, wall-door
                constructed_relationship = self._match_via_advanced_opening_host(processing_element_pairs)

            elif "bbx-" in v_pair_basis:
                # space-column, space-stair, space-wall
                constructed_relationship = self._match_via_pair_bbx(
                    pair_of_elements=processing_element_pairs,
                    match_mode=v_pair_basis,
                    reshape_x_y_z=[0.0, 0.0, 0.0],
                    factor_inclusion=0.8)
                
            else:
                print("There's another case which is superisingly not included.")
                continue

            self._add_relationship(k_pair,constructed_relationship)
        # self._print_dictionary_by_attribute('collection_all_component_relationships')

# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - StructuralSupportDependency (Subclass)
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class StructuralSupportDependency(ComponentDependencyConstructor):
    """
    Identifies structural vertical (supporting) relationships.
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    (d) Structural Support
    vertical (3 types):         column-wall, column-column, wall-wall
    Completed:                  column-wall, wall-wall, column-column
    Completed:                  slab-wall, slab-column
    -----------------------------------------------------------------------------------------
    horizontal (3 types):       column-wall, wall-wall, wall-stair
    Completed:                  column-wall, wall-wall, 
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    """

    # TODO: For the StructuralSupportRelationship class
    # try to add a general structural filter.
    # for example: if not self._is_a_structural_element(element_a):
    
    def __init__(self, doc, type_name, dependency_matix=dict()):
        self.collection_all_elements = {}
        self.collection_all_element_pairs = {}
        self.collection_all_component_relationships = {}
        self.dependency_matix = dependency_matix if dependency_matix else defaultdict()
        
        self._set_relation_type(type_name)
        self._set_relation_settings(doc)
        self._get_overall_geo_values()

    def construct_relationships(self):
        
        for k_pair, v_pair_basis in self.dependency_matix.items():

            processing_element_pairs = self.collection_all_element_pairs[k_pair]
            
            if "bbx" in v_pair_basis:
                if "same" in v_pair_basis:
                    constructed_relationship = self._match_via_pair_bbx(
                        pair_of_elements=processing_element_pairs,
                        match_mode=v_pair_basis,
                        match_level=v_pair_basis,
                        reshape_x_y_z=[0.0, 0.0, 0.0],
                        )
                else:
                    constructed_relationship = self._match_via_pair_bbx(
                        pair_of_elements=processing_element_pairs,
                        match_mode=v_pair_basis,
                        match_level=v_pair_basis,
                        reshape_x_y_z=[0.0, 0.0, self.max_slab_thickness],
                        )
            elif v_pair_basis == "slab-level":
                #slab-wall, slab-column
                constructed_relationship = self._match_via_level_id(processing_element_pairs)
            
            else:
                print("There's another case which is superisingly not included.")
                continue

            self._add_relationship(k_pair,constructed_relationship)

        self._clean_repeating_non_directed_pairs("wall-wall")
        self._clean_repeating_non_directed_pairs("column-column")
        # self._print_dictionary_by_attribute('collection_all_component_relationships')

# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - LocationalAlignmentDependency (Subclass)
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class LocationalAlignmentDependency(ComponentDependencyConstructor):
    """
    Identifies locational alignment relationships (mainly for horizontal reasoning).
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    (e) Locational Alignment
    In total (4 types):         wall-wall, wall-column, column-column, wall-stair
    Completed:                  wall-wall, wall-column
    ToFigureOut                 column-column
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ====== ======
    """

    def __init__(self, doc, type_name, dependency_matix=dict()):
        self.collection_all_elements = {}
        self.collection_all_element_pairs = {}
        self.collection_all_component_relationships = {}
        self.dependency_matix = dependency_matix if dependency_matix else defaultdict()
        
        self._set_relation_type(type_name)
        self._set_relation_settings(doc)
        self._get_overall_geo_values()
    
    def construct_relationships(self):
        
        for k_pair, v_pair_basis in self.dependency_matix.items():

            processing_element_pairs = self.collection_all_element_pairs[k_pair]
            if v_pair_basis == "line-line-alignment-same":
                
                delta_align = self.max_wall_thickness*2 # this maximum thresholds is to be tuned.
                constructed_relationship = self._match_alignment_line_line(
                        pair_of_elements=processing_element_pairs,
                        t_alignment=delta_align,
                        match_mode=v_pair_basis,
                        match_level=v_pair_basis,
                        ) 
            
            elif v_pair_basis == "line-point-alignment-same":
                
                delta_align = self.max_wall_thickness + self.max_column_thickness
                constructed_relationship = self._match_alignment_line_point(
                        pair_of_elements=processing_element_pairs,
                        t_alignment=delta_align,
                        match_mode=v_pair_basis,
                        match_level=v_pair_basis,
                        )

            # # "column-column": "group-point-alignment-same", # this is super expensive      
            # elif v_pair_basis == "group-point-alignment-same":
            #     group_point_size = 4
            #     constructed_relationship = self._match_alignment_group_of_points(
            #             pair_of_elements=processing_element_pairs,
            #             t_alignment=group_point_size,
            #             )
            
            else:
                print("There's another case which is superisingly not included.")
                continue

            self._add_relationship(k_pair,constructed_relationship)

        self._clean_repeating_non_directed_pairs("wall-wall")
        # self._clean_repeating_non_directed_pairs("column-column")
        
# # save for reasoning higher-level accessibility relationships.
# # CLASS - VerticalAccessibilityRelationship (Subclass)
# # =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# class VerticalAccessibilityDependency(ComponentDependencyConstructor):
#     """
#     Identifies vertical accessibility relationships:
#     """
#     def __init__(self, doc, type_name):

#         self._set_relation_type(type_name)
#         self._set_relation_settings(doc)
#         self.collection_all_elements = {}
#         self.collection_all_element_pairs = {}
#         self.collection_all_component_relationships = {}
    
#     def construct_relationships_from_built_pairs(self, pairs_stair_stair, pairs_room_stair):
#         """
#         Constructs basic vertical accessibility relationships.
#         """

#         # === 1. Build stair connectivity graph ===
#         stair_graph = defaultdict(set)
#         for s1, s2 in pairs_stair_stair:
#             stair_graph[s1].add(s2)
#             stair_graph[s2].add(s1)

#         # === 2. Map each stair to the room(s) it's connected to ===
#         stair_to_rooms = defaultdict(set)
#         for room_id, stair_id in pairs_room_stair:
#             stair_to_rooms[stair_id].add(room_id)

#         # === 3. Generate triplets ===
#         seen_triplets = set()
#         triplets = []

#         def add_triplet(r1, mid_stairs, r2):
#             r1_, r2_ = sorted([r1, r2])
#             key = (r1_, tuple(sorted(mid_stairs)), r2_)
#             if key not in seen_triplets:
#                 triplets.append([r1_, list(mid_stairs), r2_])
#                 seen_triplets.add(key)

#         # === 3.1 Direct stair shared by two rooms ===
#         for stair_id, rooms in stair_to_rooms.items():
#             rooms = list(rooms)
#             for i in range(len(rooms)):
#                 for j in range(i + 1, len(rooms)):
#                     add_triplet(rooms[i], [stair_id], rooms[j])

#         # === 3.2 Multi-stair connections (DFS up to length 3 for safety) ===
#         for stair_start, rooms_start in stair_to_rooms.items():
#             for room_start in rooms_start:
#                 visited = set()
#                 stack = deque()
#                 stack.append((stair_start, [stair_start]))

#                 while stack:
#                     current_stair, path = stack.pop()
#                     if len(path) > 3:
#                         continue

#                     if current_stair in stair_to_rooms:
#                         for room_end in stair_to_rooms[current_stair]:
#                             if room_end != room_start:
#                                 add_triplet(room_start, path, room_end)

#                     for neighbor in stair_graph[current_stair]:
#                         if neighbor not in path:
#                             stack.append((neighbor, path + [neighbor]))

#         # === 4. Store result ===
#         self.collection_all_component_relationships["room-stair-room"] = triplets
#         self._print_dictionary_by_attribute("collection_all_component_relationships")
        
class ComponentDependencyExtractor:
    """
    Orchestrates the extraction of component instances and construction of relationships.
    This class is intended to modularize the logic currently in AInitialRun.py.
    """
    
    def __init__(self, doc, output_dir, datahandler=None):

        self.doc = doc
        self.output_dir = output_dir
        self.datahandler = datahandler
        
        # Default instance tasks using available component classes and categories
        self.instance_tasks = [
            (SlabComponent, BuiltInCategory.OST_Floors, "v-slab.json"),
            (RoomComponent, BuiltInCategory.OST_Rooms, "v-space.json"),
            (WallComponent, BuiltInCategory.OST_Walls, "v-wall.json"),
            (DoorComponent, BuiltInCategory.OST_Doors, "v-door.json"),
            (WindowComponent, BuiltInCategory.OST_Windows, "v-window.json"),
            (StructuralColumnComponent, BuiltInCategory.OST_StructuralColumns, "v-column.json"),
            (StairComponent, BuiltInCategory.OST_Stairs, "v-stair.json"),
            (SeparationLineComponent, BuiltInCategory.OST_RoomSeparationLines, "v-separationline.json"),
        ]

    def generate_and_save_instances(self, name_key="id"):
        """
        instance_tasks: list of tuples (element_class, category, filename)
        If not provided, uses the default set for this extractor.
        """
        
        instance_tasks = self.instance_tasks

        for i, (element_class, category, filename) in enumerate(instance_tasks):
            Output("DEBUG: Processing task {}/{}: element_class={}, category={}, filename={}".format(
                i+1, len(instance_tasks), element_class, category, filename))

            collector = FilteredElementCollector(self.doc).OfCategory(category).WhereElementIsNotElementType().ToElements()
            category_name = System.Enum.GetName(BuiltInCategory, category)
            Output("Extracting instances for category: {}".format(category_name))

            instance_dict = {}
            Output("DEBUG: Starting to process {} elements for category: {}".format(len(collector), category_name))
            
            for j, element in enumerate(collector):
                try:
                    Output("DEBUG: Processing element {}/{} for category {}: element_id={}".format(
                        j+1, len(collector), category_name, element.Id))
                    
                    instance = element_class(element, self.doc)
                    Output("DEBUG: Created instance: {}".format(type(instance)))
                    
                    dict_k, dict_v = extract_instance_attributes(instance, name_key=name_key)
                    Output("DEBUG: Extracted attributes - key: {}, value type: {}".format(dict_k, type(dict_v)))
                    
                    instance_dict[dict_k] = dict_v
                    Output("DEBUG: Successfully added to instance_dict")
                    
                except Exception as e:
                    Output("ERROR: Failed to process element {}/{} for category {}: {}".format(
                        j+1, len(collector), category_name, str(e)))
                    Output("ERROR: Element details - Id: {}, Type: {}".format(element.Id, type(element)))
                    # Continue with next element instead of crashing
                    continue

            output_path = os.path.join(self.output_dir, filename)
            write_json_data(output_path, instance_dict)

    def construct_and_save_relationships(self, triggers=None):
        """
        triggers: dict with keys 'accessible', 'adjacent', 'spatial', 'structural', 'locational' (all bool)
        If triggers is None or a key is missing, that step will be constructed by default.
        """

        if triggers is None:
            triggers = {}

        # AccessibleConnectivityDependency
        if triggers.get("accessible", True):
            accessible_connectivity_matrix_basis = {
                "space-door": "door-to-from",
                "space-separationline": "space-boundary",
                "space-stair": "bbx-intersection",
                "stair-stair": "bbx-intersection",
            }
            collection_accessible_connectivity = AccessibleConnectivityDependency(
                self.doc, "accessible_connectivity", accessible_connectivity_matrix_basis)
            collection_accessible_connectivity.set_common_category_scopes(
                BuiltInCategory.OST_Rooms,
                BuiltInCategory.OST_Doors,
                BuiltInCategory.OST_RoomSeparationLines,
                BuiltInCategory.OST_Stairs,
            )
            collection_accessible_connectivity.construct_relationships()
            write_json_data(
                os.path.join(self.output_dir, "e-accessible_connectivity.json"),
                collection_accessible_connectivity.collection_all_component_relationships
            )

        # AdjacentConnectivityDependency
        if triggers.get("adjacent", True):
            adjacent_connectivity_matrix_basis = {
                "slab-space": "slab-level",
                "slab-wall": "slab-level",
                "slab-column": "slab-level",
                "wall-wall": "bbx-intersection",
                "slab-stair": "bbx-intersection",
                "stair-stair": "bbx-intersection",
                "space-wall": "space-boundary",
                "wall-stair": "bbx-intersection",
            }
            collection_adjacent_connectivity = AdjacentConnectivityDependency(
                self.doc, 'adjacent_connectivity', adjacent_connectivity_matrix_basis)
            collection_adjacent_connectivity.set_common_category_scopes(
                BuiltInCategory.OST_Floors,
                BuiltInCategory.OST_Rooms,
                BuiltInCategory.OST_Walls,
                BuiltInCategory.OST_StructuralColumns,
                BuiltInCategory.OST_Stairs,
            )
            collection_adjacent_connectivity.construct_relationships()
            write_json_data(
                os.path.join(self.output_dir, "e-adjacent_connectivity.json"),
                collection_adjacent_connectivity.collection_all_component_relationships)

        # SpatialContainmentDependency
        if triggers.get("spatial", True):
            spatial_containment_matrix_basis = {
                "space-wall": "bbx-inclusion",
                "space-column": "bbx-inclusion",
                "space-stair": "bbx-inclusion",
                "wall-door": "wall-opening",
                "wall-window": "wall-opening",
            }
            collection_spatial_containment = SpatialContainmentDependency(
                self.doc, 'spatial_containment', spatial_containment_matrix_basis)
            collection_spatial_containment.set_common_category_scopes(
                BuiltInCategory.OST_Rooms,
                BuiltInCategory.OST_Walls,
                BuiltInCategory.OST_StructuralColumns,
                BuiltInCategory.OST_Stairs,
                BuiltInCategory.OST_Doors,
                BuiltInCategory.OST_Windows)
            collection_spatial_containment.construct_relationships()
            write_json_data(
                os.path.join(self.output_dir, "e-spatial_containment.json"),
                collection_spatial_containment.collection_all_component_relationships)

        # StructuralSupportDependency
        if triggers.get("structural", True):
            structural_support_matrix_basis = {
                "wall-wall": "bbx-intersection-all",
                "wall-column": "bbx-intersection-all",
                "column-column": "bbx-intersection-different",
                "slab-wall": "slab-level",
                "slab-column": "slab-level",
            }
            collection_structural_support = StructuralSupportDependency(
                self.doc, 'structural_support', structural_support_matrix_basis)
            collection_structural_support.set_common_category_scopes(
                BuiltInCategory.OST_StructuralColumns,
                BuiltInCategory.OST_Walls,
                BuiltInCategory.OST_Floors,
            )
            collection_structural_support.construct_relationships()
            write_json_data(
                os.path.join(self.output_dir, "e-structural_support.json"),
                collection_structural_support.collection_all_component_relationships
            )

        # LocationalAlignmentDependency
        if triggers.get("locational", True):
            locational_alignment_matrix_basis = {
                "wall-wall": "line-line-alignment-same",
                "wall-column": "line-point-alignment-same",
                # column-column alignment is removed due to computing capacity.
            }
            collection_locational_alignment = LocationalAlignmentDependency(
                self.doc, 'locational_alignment', locational_alignment_matrix_basis)
            collection_locational_alignment.set_common_category_scopes(
                BuiltInCategory.OST_StructuralColumns,
                BuiltInCategory.OST_Walls,
            )
            collection_locational_alignment.construct_relationships()
            write_json_data(
                os.path.join(self.output_dir, "e-locational_alignment.json"),
                collection_locational_alignment.collection_all_component_relationships
            )