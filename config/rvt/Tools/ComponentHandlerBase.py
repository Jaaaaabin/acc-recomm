#! python3
# # IMPORT - BASIC PACKAGES 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#
import clr
import os
import uuid
from collections import defaultdict

import revit_script_util
from revit_script_util import Output

clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
import Autodesk
from System.Collections.Generic import *
from System.Collections.Generic import List
from Autodesk.Revit.DB import BuiltInParameter, FilteredElementCollector, FailureProcessingResult, IFailuresPreprocessor, FailureSeverity
from Autodesk.Revit.DB import ElementId, XYZ, Line, Transaction, BuiltInCategory, Level, Group, Solid, Edge, Face

# =====================================================================================================
# IMPORT - REVIT Batch UTILITIES
import revit_script_util
from revit_script_util import Output

# =====================================================================================================
# CLASS - NoWarningsFailurePreprocessor (Assistance Class)
class NoWarningsFailurePreprocessor(IFailuresPreprocessor):
    
    # I find out that it is possible to handle this problem using new Namespace everytime.
    # reference : https://forums.autodesk.com/t5/revit-api-forum/revit-2024-in-python-node-in-dynamo-doc-loadfamily-does-not/td-p/11996943

    __namespace__ = str(uuid.uuid4()) # 

    def PreprocessFailures(self, failuresAccessor):
        fail_acc_list = failuresAccessor.GetFailureMessages()
        for failure in fail_acc_list:
            if failure.GetSeverity() == FailureSeverity.Warning:
                print("[WARNING] Suppressing warning:", failure.GetDescriptionText())
                failuresAccessor.DeleteWarning(failure)
        return FailureProcessingResult.Continue

# def suppress_warnings(transaction):
#     fail_opt = transaction.GetFailureHandlingOptions()
#     fail_opt.SetFailuresPreprocessor(NoWarningsFailurePreprocessor())
#     transaction.SetFailureHandlingOptions(fail_opt)

# class NoWarningsFailurePreprocessor(IFailuresPreprocessor):

#     def PreprocessFailures(self, failuresAccessor):
#         fail_messages = failuresAccessor.GetFailureMessages()
#         for fmsg in fail_messages:
#             if fmsg.GetSeverity() == FailureSeverity.Warning:
#                 print("\n" + "="*60)
#                 print("[INFO] Deleted Warning Message:")
#                 print("-" * 60)
#                 print(fmsg.GetDescriptionText())
#                 print("="*60 + "\n")
#                 failuresAccessor.DeleteWarning(fmsg)
#         return FailureProcessingResult.Continue

# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - ComponentHandlerBase (Base Class)
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class ComponentHandlerBase:
    """
    Base class for constructing dependencies between Revit elements.
    """
    def __init__(self):

        self.design_revision_info = defaultdict()   # Just a placeholder. 
        self.handler_type = None                    # Placeholder for handler type (e.g., "Stair", "Wall", "Door")
        self.room_bdry_edge = None

    def _load_component_families(self, doc, family_directory):
        """
        Load all .rfa family files from immediate subfolders under the given directory.
        Assumes there are no sub-subfolders.
        """
        if not os.path.isdir(family_directory):
            print("[ERROR] Invalid folder path: {}".format(family_directory))
            return

        for subfolder in os.listdir(family_directory):
            
            family_paths = []
            
            # iterate through all subfolders, each representing a group of component families.
            sub_path = os.path.join(family_directory, subfolder)
            
            if os.path.isdir(sub_path):
                for file in os.listdir(sub_path):

                    # Check if the file is a Revit family file
                    if file.lower().endswith(".rfa"):
                        full_path = os.path.join(sub_path, file)
                        family_paths.append(full_path)
                        
            try:
                # Load the family into the document
                with Transaction(doc, 'Load All Families'):
                    for f_p in family_paths:
                        doc.LoadFamily(f_p)
                        print("[INFO] Loaded family: {}".format(f_p))
            except Exception as e:
                print("[ERROR] Failed to load {}: {}".format(f_p, e))
            
            # # to activate the family symbols (if any)
            # symbol_ids = list(family.GetFamilySymbolIds())                            
            # if symbol_ids:
                
            #     symbol = doc.GetElement(symbol_ids[0])
                
            #     if not symbol.IsActive:
                    
            #         t = Transaction(doc, "Activate Symbol: {}".format(symbol.Name))
            #         t.Start()
            #         symbol.Activate()
            #         t.Commit()
            #         print("[INFO] Activated symbol: {}".format(symbol.Name))
            
            # else:
            #     print("[WARNING] No symbols found in: {}".format(file))
        
            # # to activate all the family symbols (worst option)
            # symbols = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
    
    def _count_element_types_by_category(self, doc, built_in_category):
        """
        For a given BuiltInCategory (e.g., OST_Walls), count how many instances
        exist per element type, and extract the first instance's ElementId for each type.

        Returns:
            List of tuples sorted by count, each tuple is:
            (type_name, count, first_instance_element_id)
        """
        # Step 1: Get all element types in the category
        type_elements = FilteredElementCollector(doc) \
            .OfCategory(built_in_category) \
            .WhereElementIsElementType() \
            .ToElements()

        # Map: type_id -> type_name
        type_id_to_name = {
            et.Id: et.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
            for et in type_elements
        }

        # Step 2: Get all instances in the category
        instances = FilteredElementCollector(doc) \
            .OfCategory(built_in_category) \
            .WhereElementIsNotElementType() \
            .ToElements()

        # Map: type_name -> (count, first_element_id)
        type_stats = {}

        for inst in instances:
            type_id = inst.GetTypeId()
            type_name = type_id_to_name.get(type_id)
            if not type_name:
                continue

            if type_name not in type_stats:
                type_stats[type_name] = [0, inst.Id]  # count, first_id
            type_stats[type_name][0] += 1

        # Step 3: Sort by count (descending)
        sorted_results = sorted(
            [(type_name, count, first_id) for type_name, (count, first_id) in type_stats.items()],
            key=lambda x: x[1],
            reverse=True
        )

        return sorted_results
    
    def _get_default_reference_component_id(self, doc, component_ost_catgegory):
        
        # BuiltInCategory.OST_Doors        
        # BuiltInCategory.OST_Walls
        
        counted_components_by_type = self._count_element_types_by_category(doc, component_ost_catgegory)
        reference_component_id = counted_components_by_type[0][-1] if counted_components_by_type else None
        reference_component_id = ElementId(reference_component_id) if not isinstance(reference_component_id, ElementId) else reference_component_id
        
        return reference_component_id
        
    def _get_sorted_levels(self, doc):
        """
        Retrieves all Levels in the model and returns them sorted by Elevation (lowest to highest).
        """
        
        self.all_sorted_levels = []

        levels = FilteredElementCollector(doc).OfClass(Autodesk.Revit.DB.Level).ToElements()
        sorted_levels = sorted(levels, key=lambda lvl: lvl.Elevation)
 
        for lvl in sorted_levels:
            self.all_sorted_levels.append([str(lvl.Id), lvl.Elevation])
    
    def _find_level_above_room(self, room):
        """
        Given a room element, find the next level whose elevation is >= room base elevation + room height.
        """
        room_lv = str(room.LevelId)

        # Find the elevation of the room's current level
        base_elevation = None
        for lv, elev in self.all_sorted_levels:
            if room_lv == lv:
                base_elevation = elev
                break

        # Estimate room height from its bounding box
        bbx = room.get_BoundingBox(None)
        target_elevation = base_elevation + (bbx.Max.Z - bbx.Min.Z)

        # Find the next level at or above the top of the room
        for lv, elev in self.all_sorted_levels:
            if elev >= target_elevation:
                return lv
            
        print("Warning: No level found above the top of the room.")
        return None
    
    def _find_floor_closest_to_level(self, target_level, max_elev_diff_allowed=0.5):
        """
        Find the floor slab that is closest to the specified Level (through LevelId corresponding to Level.Elevation).
        """
        
        target_elev = target_level.Elevation
        closest_floor = None
        min_elev_diff_floor_level = float("inf")

        level_map = {
            lvl.Id: lvl
            for lvl in FilteredElementCollector(self.doc).OfClass(Level).ToElements()
        }

        floors = FilteredElementCollector(self.doc)\
            .OfCategory(BuiltInCategory.OST_Floors)\
            .WhereElementIsNotElementType()\
            .ToElements()

        for floor in floors:

            lvl_id = floor.LevelId

            if lvl_id in level_map:
                floor_lvl = level_map[lvl_id]
                elev_diff = abs(floor_lvl.Elevation - target_elev)
                if elev_diff < min_elev_diff_floor_level:
                    min_elev_diff_floor_level = elev_diff
                    closest_floor = floor

        if closest_floor:
            if min_elev_diff_floor_level > max_elev_diff_allowed:
                Output("[WARNING-HandlerBase] Closest floor elevation difference ({:.2f}) exceeds threshold ({:.2f}).".format(
                    min_elev_diff_floor_level, max_elev_diff_allowed))
                
            Output("[INFO-HandlerBase] Closest floor found at level '{}', Elevation diff: {:.2f}".format(
                level_map[closest_floor.LevelId].Name, min_elev_diff_floor_level))
        else:
            Output("[WARNING-HandlerBase] No floor matched to level {}".format(target_level.Name))

        return closest_floor
    
    def _get_clipped_corner_points(self, unique_points, center, room_bdry_edge_in_meter):
        """
        Shrinks each corner point inward toward the center by a fixed distance.

        Parameters:
            unique_points (List[XYZ]): List of corner points (on room floor).
            center (XYZ): Room center point (2D projected).
            cut_distance (float): Offset distance in meters.

        Returns:
            List[XYZ]: List of clipped corner points.
        """
        clipped_points = []

        print("[INFO] Room center point: X = {:.3f}, Y = {:.3f}, Z = {:.3f}".format(center.X, center.Y, center.Z))

        for pt in unique_points:
            direction = center.Subtract(pt)
            try:
                dir_unit = direction.Normalize()
                clipped_pt = pt.Add(dir_unit.Multiply(room_bdry_edge_in_meter))
                clipped_points.append(clipped_pt)
            except:
                print("[WARNING] Failed to normalize direction from point to center (possibly coincident).")
                continue

        # if len(clipped_points) > 4:
        #     clipped_points.sort(key=lambda p: p.DistanceTo(center), reverse=True)
        #     clipped_points = clipped_points[:4]

        return clipped_points

    def _get_feature_points_of_a_room_by_closedshell(
        self, room, geo_tolerance=0.5,):

        # IMPORTANT
        # ==================================================================================
        # NOTE: In Revit, The column should all be set as NON room boundary elements.
        # ==================================================================================
        
        # Attention: Room center is fully dependent on the placed crosses.
        center_temporary = room.Location.Point 
        shell = room.ClosedShell

        if not shell:
            print("[ERROR] Room has no ClosedShell.")
            return []

        # Step 1: First pass to determine minimum Z
        min_z = None
        for geom_obj in shell:
            solid = geom_obj if isinstance(geom_obj, Solid) else None
            if not solid:
                continue
            for face in solid.Faces:
                for edge_loop in face.EdgeLoops:
                    for edge in edge_loop:
                        curve = edge.AsCurve()
                        for pt in [curve.GetEndPoint(0), curve.GetEndPoint(1)]:
                            if min_z is None or pt.Z < min_z:
                                min_z = pt.Z

        if min_z is None:
            print("[ERROR] Could not determine minimum Z.")
            return []

        # Step 2: Second pass to collect only floor-level unique points
        unique_points = []

        def is_far_enough(new_pt):
            return all(new_pt.DistanceTo(existing_pt) >= geo_tolerance for existing_pt in unique_points)

        for geom_obj in shell:
            solid = geom_obj if isinstance(geom_obj, Solid) else None
            if not solid:
                continue
            for face in solid.Faces:
                for edge_loop in face.EdgeLoops:
                    for edge in edge_loop:
                        curve = edge.AsCurve()
                        for pt in [curve.GetEndPoint(0), curve.GetEndPoint(1)]:
                            if abs(pt.Z - min_z) < geo_tolerance and is_far_enough(pt):
                                unique_points.append(XYZ(pt.X, pt.Y, min_z))
        
        # clipped_pts = self._get_clipped_corner_points(unique_points, center_temporary, room_bdry_edge_in_meter=room_bdry_edge_in_meter)
        # print("[INFO] Unique Room Shell Points ({} total):".format(len(unique_points)))
        # for i, pt in enumerate(unique_points):
        #     print("Point {:02d}: X={:.3f}, Y={:.3f}, Z={:.3f}".format(i + 1, pt.X, pt.Y, pt.Z))
        # print("[INFO] Clipped Points ({} total):".format(len(clipped_pts)))
        # for i, pt in enumerate(clipped_pts):
        #     print("Point {:02d}: X={:.3f}, Y={:.3f}, Z={:.3f}".format(i + 1, pt.X, pt.Y, pt.Z))
        
        feature_points = {}
        feature_points["0"] = center_temporary
        for idx, pt in enumerate(unique_points):
            key = str(idx + 1)
            feature_points[key] = pt
        # print ("feature_points", feature_points)

        return feature_points
    
    def _get_room_relevant_wall_placement_point(
        self, room, wall, location_index=0):
        """
        Projects room feature points (e.g., center, corners) onto a wall's location line and
        returns a contextually appropriate point along the wall (for door/stair placement).

        Parameters:
            room: Revit Room element
            wall: Revit Wall element (must have Location.Curve)
            room_bdry_edge_in_meter: Margin from room boundary when generating sample points
            location_index: Index into prioritized t-values (0 = center, 1/2 = left/right)

        Returns:
            XYZ: Wall placement point (or None if projection fails)
        """
        location_curve = wall.Location.Curve
        if not location_curve:
            print("[ERROR] Wall has no location curve.")
            return None

        # 1. Get room sample points (center and offset)
        room_feature_points = self._get_feature_points_of_a_room_by_closedshell(room)

        # 2. Project the room featured points to the boundary wall
        projection_results = {}
        for key, point in room_feature_points.items():
            
            t_val = self._find_projection_point_on_wall_from_point(point, wall)
            if t_val is not None:
                projection_results[key] = t_val
            else:
                print("[WARNING] Failed to project {} to wall.".format(key))

        t_scopes = self._get_prioritized_t_scopes(projection_results)

        location_curve = wall.Location.Curve
        location_index = int(location_index)
        placement_point = location_curve.Evaluate(t_scopes[location_index], False)
    
        return placement_point
        
    def  _find_projection_point_on_wall_from_point(self, outside_point, wall):
        """
        Projects the center of the room perpendicularly onto the wall's location line,
        and returns the closest point on the wall curve along with the parameter t.

        Returns:
            projected_point (XYZ): The projected point on the wall.
            t_value (float): Normalized parameter along the curve (0 to 1).
            distance (float): Distance from room center to projected point.
        """

        curve = wall.Location.Curve

        # Make sure the curve is a straight line (walls usually are)
        if not isinstance(curve, Line):
            print("[WARNING] Wall curve is not a line. Projection skipped.")
            return None
        
        # print ("curve:", curve)
        # print ("outside_point:", outside_point)
        # Project the room center onto the wall line
        try:
            result = curve.Project(outside_point)
        except Exception as e:
            print("[ERROR] Exception during projection: {}".format(e))
            return None
        
        if result is None:
            print("[WARNING] Projection failed.")
            return None

        t_value = result.Parameter

        # # The following can also be exported. 
        # projected_point = result.XYZPoint       
        # distance = outside_point.DistanceTo(projected_point)

        return t_value
    
    def _get_prioritized_t_scopes(
        self,
        projection_results,):
        """
        Extracts and returns a prioritized list of t-values from projection results:
        - Always includes the value for key "0" (center) as the first item.
        - Appends the min and max of the other values, if they are different from center.

        Args:
            projection_results (dict): Dictionary of key -> t-value (float or None)

        Returns:
            List[float]: Prioritized list of t-values [center, min, max]

        TODO: handler the cases that the wall is a very partial one. works. might need recheck.
        """

        # Step 1: Get center t which is temporary and dependent on the room placement point in revit.
        # this step is only here for potential future use.
        t_scopes = []
        t_center_temporary = projection_results.get("0", None)
        if t_center_temporary is None:
            print("[ERROR] Center point projection failed. Cannot compare.")
            return t_scopes

        # Step 2: Collect other t-values (excluding None)
        other_t_vals = [val for key, val in projection_results.items() if key != "0" and val is not None]

        if not other_t_vals:
            return t_scopes
        
        t_min = min(other_t_vals)
        t_max = max(other_t_vals)
        t_center = (t_min + t_max) / 2.0
        t_scopes.append(t_center)

        # Step 3: Add min and max if sufficiently different from center
        def shift_toward_center_fixed(t, center, delta):
            if t < center:
                return min(t + delta, center)
            elif t > center:
                return max(t - delta, center)
            else:
                return center

        if abs(t_min - t_center) > 1e-6:
            if self.room_bdry_edge is not None and self.room_bdry_edge != 0:
                t_min_shifted = shift_toward_center_fixed(t_min, t_center, self.room_bdry_edge)
                t_scopes.append(t_min_shifted)
            else:
                t_scopes.append(t_min)

        if abs(t_max - t_center) > 1e-6 and t_max != t_min:
            if self.room_bdry_edge is not None and self.room_bdry_edge != 0:
                t_max_shifted = shift_toward_center_fixed(t_max, t_center, self.room_bdry_edge)
                t_scopes.append(t_max_shifted)
            else:
                t_scopes.append(t_max)

        return t_scopes

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

    def _delete_one_element(self, doc, element_id):
        """
        Deletes a Revit element from the document by its ElementId.

        Parameters:
            element_id (ElementId or int): The ID of the element to delete.
        """

        if isinstance(element_id, int):
            element_id = ElementId(element_id)

        element = doc.GetElement(element_id)

        if not element:
            print("[WARNING] No element found with ID: {}".format(element_id))
            return
        
        if doc.IsModifiable:
            print("[ERROR] Document is already in a modifiable state. Cannot start transaction.")
            return
        
        t = Transaction(doc, "Delete Element")
        try:
            t.Start()
            doc.Delete(element.Id)
            t.Commit()
            print("[INFO] Successfully deleted element ID: {}".format(element_id))     
        except Exception as e:
            print("[ERROR] Exception while deleting element ID {}: {}".format(element_id, e))
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()

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
    
    # # -------------------------------------------------------------------------------------------
    # # TODO: function for grouping building components.
    # # This function is subject to change or to be leveraged in other modules in the future.
    # def _group_elements_by_ids(self, element_ids, group_name="GroupedElements"):
    #     """
    #     Groups a list of elements into a group.
    #     Returns: Group element if successful, otherwise None.
    #     """
    #     if not element_ids or not isinstance(element_ids, list):
    #         print("[ERROR] Please provide a list of element IDs.")
    #         return None

    #     # Convert to ElementId if input are raw integers
    #     ids = []
    #     for eid in element_ids:
    #         if isinstance(eid, int):
    #             ids.append(ElementId(eid))
    #         elif isinstance(eid, ElementId):
    #             ids.append(eid)
    #         else:
    #             print("[WARNING] Ignored invalid ID: {}".format(eid))

    #     if not ids:
    #         print("[ERROR] No valid element IDs to group.")
    #         return None

    #     t = Transaction(self.doc, "Create Element Group")
    #     try:
    #         t.Start()
    #         group = self.doc.Create.NewGroup(List[ElementId](ids))
    #         group.GroupType.Name = group_name
    #         t.Commit()
    #         print("[INFO] Group created successfully with name: {}".format(group_name))
    #         return group
    #     except Exception as e:
    #         print("[ERROR] Failed to create group: {}".format(e))
    #         if t.HasStarted():
    #             t.RollBack()
    #         return None
    
    # # -------------------------------------------------------------------------------------------
    # # TODO: function for retrievign the information of the existing groups (of building components).
    # # This function needs check for the output information.
    # def _get_existing_groups(self, verbose=True):
    #     """
    #     Retrieves all existing group instances in the project,
    #     and returns a dictionary of unique group names to one instance of each group.

    #     Parameters:
    #         verbose (bool): Whether to print detailed info for each group.

    #     Returns:
    #         dict: {group_name (str): Group (Element)}
    #     """
    #     try:
    #         collector = FilteredElementCollector(self.doc).OfClass(Group).ToElements()
    #         group_dict = {}

    #         for group in collector:
    #             group_name = group.Name
    #             if group_name not in group_dict:
    #                 group_dict[group_name] = group

    #                 if verbose:
    #                     # print("\n[INFO] Group Name: {}".format(group_name))
    #                     # print("  - GroupType: {}".format(group.GroupType.Name))
    #                     # print("  - GroupType ID: {}".format(group.GroupType.Id.IntegerValue))
    #                     member_ids = group.GetMemberIds()
    #                     member_id_list = [eid.IntegerValue for eid in member_ids]
    #                     print("  - Member Element IDs: {}".format(member_id_list))

    #         print("\n[INFO] Found {} unique groups in project.".format(len(group_dict)))
    #         return group_dict

    #     except Exception as e:
    #         print("[ERROR] Failed to retrieve groups: {}".format(e))
    #         return {}