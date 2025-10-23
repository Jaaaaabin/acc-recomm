#! python3
# # IMPORT - BASIC PACKAGES 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#
import clr

import revit_script_util
from revit_script_util import Output

clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
from System.Collections.Generic import *
from System.Collections.Generic import List
from Autodesk.Revit.DB import FilteredElementCollector, ElementTransformUtils
from Autodesk.Revit.DB import ElementId, XYZ, Line, Transaction
from Autodesk.Revit.DB import Wall, WallType, Level, BuiltInParameter

# IMPORT - CUSTOM FUNCTIONS. 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#
from Tools.ComponentHandlerBase import NoWarningsFailurePreprocessor, ComponentHandlerBase

# FUNCTIONS 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#

# CLASS - ComponentHandlerWall (Subclass)
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# ========= "WALL" =========
# WALL	CREATE	Space	CREATE a WALL in relation to the specific Space
# ------------------------------------------------------------------------------------------------------
# WALL	MODIFY	Space	MODIFY a WALL in relation to the specified Space
# ------------------------------------------------------------------------------------------------------
# WALL	SWAP	Element Family Type	SWAP a WALL to another WALL of a different Element Family Type
# WALL	SWAP	Element Property	SWAP a WALL to another WALL with different Element Properties
# ------------------------------------------------------------------------------------------------------
# WALL	DELETE	Element	DELETE a Element (WALL)
# ------------------------------------------------------------------------------------------------------
class ComponentHandlerWall(ComponentHandlerBase):
    """
    Handler class for wall related functions.
    main functions:
    _create_wall_by_shifting:              Explanation.
    wall_movement_by_shifting:              Explanation.
    """

    def __init__(self, doc, enable_group_handling=True):
        
        self.doc = doc
        self._get_sorted_levels(doc)

        self.enable_group_handling = enable_group_handling
    
    def _get_wall_loc_points(self, wall):
        wall_location = wall.Location.Curve
        return (wall_location.GetEndPoint(0), wall_location.GetEndPoint(1))
    
    # ================================================
    # ================================================
    # ================================================
    # ================  C R E A T E  =================
    # ================================================
    # ================================================
    # ================================================
    def wall_create(self, ref_room_id, ref_wall_id, params_wall_create=None):
        """
        # WALL	CREATE	Space	        CREATE a WALL in relation to the specific Space
        """
        # TODO:  use ref_room_id to guide the wall creation.
        
        if params_wall_create is None:
            params_wall_create = [0.1] # Default
        offset_normal_distance = params_wall_create

        creation_parameters = self._get_wall_shifting_creation_parameters(ref_wall_id, offset_normal_distance)
        
        wall_location, wall_height, wall_type, wall_level = creation_parameters
        
        Output("[INFO] wall_create: parameters are set.")

        # Attention, creation of an additional wall will cause too much trouble here on theoretical level.
        return self._create_wall_at_location(wall_location, wall_height, wall_type, wall_level)
        
    def _get_wall_shifting_creation_parameters(self, ref_wall_id, offset_distance=100.0):
        """
        Creates a new wall by offsetting an existing wall along its normal direction.

        Parameters:
            ref_wall (Wall): The existing wall to reference.
            offset_distance (float): Distance to shift the new wall in the normal direction.
        """
        
        if isinstance(ref_wall_id, int):
            ref_wall_id = ElementId(ref_wall_id)

        ref_wall = self.doc.GetElement(ref_wall_id)

        try:
            # 1. Get original points
            p1, p2 = self._get_wall_loc_points(ref_wall)

            # 2. Compute normal direction
            direction = p2.Subtract(p1).Normalize()
            up = XYZ.BasisZ
            normal = direction.CrossProduct(up).Normalize()

            # 3. Shift both points
            p1_offset = p1.Add(normal.Multiply(offset_distance))
            p2_offset = p2.Add(normal.Multiply(offset_distance))

            wall_type = self.doc.GetElement(ref_wall.GetTypeId())
            wall_level = self.doc.GetElement(ref_wall.LevelId)

            height_param = ref_wall.get_Parameter(BuiltInParameter.WALL_USER_HEIGHT_PARAM)
            wall_height = height_param.AsDouble() if height_param and height_param.HasValue else 3.0*3.048  # Default to 3 meters if not set
            
            # 4. Create new wall line & create wall
            wall_location = Line.CreateBound(p1_offset, p2_offset)
            Output("[INFO-HandlerWall] wall location is created.")

            return (wall_location, wall_height, wall_type, wall_level)

        except Exception as e:
            Output("[ERROR] Failed to shift and create wall.")
            return None
        
    def _create_wall_at_location(
        self,
        wall_location=None,
        wall_height=3.0*3.048,
        wall_type=None,
        wall_level=None):
        """
        Creates a wall using a line defined by start and end XYZ points (location-centered).
        """

        if not wall_type:
            wall_type = FilteredElementCollector(self.doc).OfClass(WallType).FirstElement()

        if not wall_level:
            wall_level = FilteredElementCollector(self.doc).OfClass(Level).FirstElement()

        t = Transaction(self.doc, "Create Wall")
        try:
            t.Start()
            wall = Wall.Create(
                self.doc,
                wall_location,
                wall_type.Id,
                wall_level.Id,
                wall_height, # float
                0.0, # float
                False, # boolean
                False, # boolean
            )

            # set the room bounding parameter to false
            param = wall.get_Parameter(BuiltInParameter.WALL_ATTR_ROOM_BOUNDING)
            if param and not param.IsReadOnly:
                param.Set(0)  # 0 = False

            t.Commit()
            Output("[ININFO-HandlerWallFO] Wall created successfully.")
            return wall
        
        except Exception as e:
            Output("[ERROR] Failed to create wall.")
            t.RollBack()
            return None

    # ============================================================================================================
    # NEW
    def _partition_targets_by_group(self, element_ids):
        """
        Partition elements into groups vs standalone.
        """
        invalid = ElementId.InvalidElementId
        group_int_ids = set()
        standalone_ids = List[ElementId]()

        for eid in element_ids:
            el = self.doc.GetElement(eid)
            if el is None:
                continue
            gid = self._get_group_id_or_invalid(el)
            if gid != invalid:
                group_int_ids.add(gid.IntegerValue)
            else:
                standalone_ids.Add(eid)

        group_ids = [ElementId(i) for i in group_int_ids]
        return group_ids, standalone_ids
    
    def _move_elements_group_aware(self, element_ids_to_move, move_vector):
        """Group-aware movement logic."""
        group_ids, standalone_ids = self._partition_targets_by_group(element_ids_to_move)
        
        if group_ids:
            Output("[INFO-HandlerWall] Found {} group(s) containing wall components.".format(len(group_ids)))
        if standalone_ids.Count > 0:
            Output("[INFO-HandlerWall] Found {} standalone element(s) to move.".format(standalone_ids.Count))

        # Phase 1: Move groups
        for gid in group_ids:
            ginst = self.doc.GetElement(gid)
            if ginst is None:
                continue
            try:
                if hasattr(ginst, "Pinned") and ginst.Pinned:
                    Output("[INFO-HandlerWall] Group {} is pinned. Skipping.".format(gid.IntegerValue))
                    continue
                ElementTransformUtils.MoveElement(self.doc, gid, move_vector)
                Output("[INFO-HandlerWall] Moved group: {}".format(gid.IntegerValue))
            except Exception as ge:
                Output("[WARN-HandlerWall] Failed to move group {}: {}".format(gid.IntegerValue, str(ge)))

        # Phase 2: Move standalone elements
        if standalone_ids.Count > 0:
            try:
                ElementTransformUtils.MoveElements(self.doc, standalone_ids, move_vector)
                Output("[INFO-HandlerWall] Moved {} standalone elements.".format(standalone_ids.Count))
            except Exception as ee:
                Output("[WARN-HandlerWall] Failed to move standalone elements: {}".format(str(ee)))

    def _copy_elements_group_aware(self, element_ids_to_copy, move_vector):
        """
        Group-aware copying logic.
        """
        group_ids, standalone_ids = self._partition_targets_by_group(element_ids_to_copy)
        all_new_ids = List[ElementId]()

        # Phase 1: Copy groups
        for gid in group_ids:
            try:
                copied_group_ids = ElementTransformUtils.CopyElement(self.doc, gid, move_vector)
                for cid in copied_group_ids:
                    all_new_ids.Add(cid)
                Output("[INFO-HandlerWall] Copied group: {} -> {}".format(gid.IntegerValue, copied_group_ids[0].IntegerValue))
            except Exception as ge:
                Output("[WARN-HandlerWall] Failed to copy group {}: {}".format(gid.IntegerValue, str(ge)))

        # Phase 2: Copy standalone elements
        if standalone_ids.Count > 0:
            try:
                copied_standalone_ids = ElementTransformUtils.CopyElements(self.doc, standalone_ids, move_vector)
                for cid in copied_standalone_ids:
                    all_new_ids.Add(cid)
                Output("[INFO-HandlerWall] Copied {} standalone elements.".format(standalone_ids.Count))
            except Exception as ee:
                Output("[WARN-HandlerWall] Failed to copy standalone elements: {}".format(str(ee)))
                
        return all_new_ids

    def _get_group_id_or_invalid(self, el):
        """Return owning GroupId or InvalidElementId if none."""
        invalid = ElementId.InvalidElementId
        try:
            gid = el.GroupId  # many elements expose this
            return gid if gid and gid != invalid else invalid
        except:
            return invalid
    # NEW
    # ============================================================================================================

    # ================================================
    # ================================================
    # ================================================
    # ================  M O D I F Y  =================
    # ================================================
    # ================================================
    # ================================================
    def wall_modify(self, ref_room_id, ref_wall_id, params_wall_modify=None, use_group_handling=None):
        """
        # WALL	MODIFY	Space	        MODIFY a WALL in relation to the specified Space
        """
        group_handling_active = (use_group_handling if use_group_handling is not None 
                               else self.enable_group_handling)
        
        if params_wall_modify is None:
            params_wall_modify = [0.1] # Default

        offset_normal_distance = params_wall_modify

        if isinstance(ref_wall_id, int):
            ref_wall_id = ElementId(ref_wall_id)

        ref_wall = self.doc.GetElement(ref_wall_id)

        if not ref_wall or not hasattr(ref_wall, "Location") or not hasattr(ref_wall.Location, "Curve"):
            
            Output("[ERROR] Invalid wall or wall has no location curve.")
            return None
        
        Output("[INFO-HandlerWall] wall_modify: before trying the execution.")

        try:
            # 1. Get original location points
            p1, p2 = self._get_wall_loc_points(ref_wall)

            # 2. Calculate wall direction and normal
            direction = p2.Subtract(p1).Normalize()
            up = XYZ.BasisZ
            normal = direction.CrossProduct(up).Normalize()

            # 3. Compute offset vector
            move_vector = normal.Multiply(offset_normal_distance)

            # 4. Collect elements to move (including related elements like doors/windows)
            element_ids_to_move = List[ElementId]()
            element_ids_to_move.Add(ref_wall_id)

            # Optional: Add hosted elements (doors, windows, etc.)
            try:
                hosted_elements = ref_wall.FindInserts(True, True, True, True)  # all insert types
                for hosted_id in hosted_elements:
                    element_ids_to_move.Add(hosted_id)
                    Output("[INFO-HandlerWall] Added hosted element: {}".format(hosted_id.IntegerValue))
            except:
                Output("[INFO-HandlerWall] No hosted elements found or unable to retrieve them.")

            # 4. Move the wall
            t = Transaction(self.doc, "Shift Wall")
            
            options = t.GetFailureHandlingOptions()
            options.SetFailuresPreprocessor(NoWarningsFailurePreprocessor())
            t.SetFailureHandlingOptions(options)

            t.Start()
            try:
                # ==================== MODULAR MOVEMENT LOGIC ====================
                if group_handling_active:
                    Output("[INFO-HandlerWall] Using group-aware movement.")
                    self._move_elements_group_aware(element_ids_to_move, move_vector)
                else:
                    Output("[INFO-HandlerWall] Using simple movement.")
                    ElementTransformUtils.MoveElements(self.doc, element_ids_to_move, move_vector)
                # ================================================================
                
                t.Commit()
                Output("[INFO-HandlerWall] Wall shifted successfully.")
                return ref_wall
            
            except Exception as e:
                Output("[ERROR-HandlerWall] Failed to shift wall: {}".format(str(e)))
                t.RollBack()
                return None

        except Exception as e:
            Output("[ERROR-HandlerWall] Failed to shift wall: {}".format(str(e)))
            if 't' in locals() and t.HasStarted():
                t.RollBack()
            return None

    # ================================================
    # ================================================
    # ================================================
    # ================  D E L E T E  =================
    # ================================================
    # ================================================
    # ================================================
    def wall_delete(self, ref_wall_id):
        """
        # WALL	DELETE	Element	DELETE a Element (WALL)
        #TODO: 
        # to test: add warning handlers for automatically handling rooms.
        # Tested already: when room is affected, it can be reverted
        """
        if isinstance(ref_wall_id, int):
            ref_wall_id = ElementId(ref_wall_id)

        ref_wall = self.doc.GetElement(ref_wall_id)
        if not ref_wall:
            Output("[ERROR] Cannot find the wall to delete.")
            return None

        try:
            t = Transaction(self.doc, "Delete Wall")
            t.Start()
            self.doc.Delete(ref_wall.Id)
            t.Commit()
            Output("[INFO] Wall deleted successfully.")
            return True
        
        except Exception as e:
            Output("[ERROR] Failed to delete wall.")
            if t.HasStarted():
                t.RollBack()
            return None
        
    # ================================================
    # ================================================
    # ================================================
    # ================  S  W  A  P  ==================
    # ================================================
    # ================================================
    # ================================================
    # # TODO: to test later.
    