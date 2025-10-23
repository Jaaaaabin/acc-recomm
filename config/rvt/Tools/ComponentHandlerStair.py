#! python3
# # IMPORT - BASIC PACKAGES 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#
import clr
import traceback

import revit_script_util
from revit_script_util import Output

clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
import Autodesk
from System.Collections.Generic import *
from System.Collections.Generic import List
from Autodesk.Revit.DB import ElementTransformUtils, IFailuresPreprocessor
from Autodesk.Revit.DB import ElementId, XYZ, Line, Transaction, StairsEditScope, LocationCurve

from Autodesk.Revit.DB.Architecture import StairsRun, StairsLanding, StairsRunJustification 
from RevitServices.Transactions import TransactionManager

# =====================================================================================================
# IMPORT - REVIT Batch UTILITIES
import revit_script_util
from revit_script_util import Output

# =====================================================================================================
# IMPORT - CUSTOM FUNCTIONS. 
from Tools.ComponentHandlerBase import NoWarningsFailurePreprocessor, ComponentHandlerBase
from Tools.GeneralSettings import convert_python_to_curve_list
from Tools.ComponentHandlerSlab import ComponentHandlerSlab

# =====================================================================================================
# CLASS - ComponentHandlerStair (Subclass)
# ========= "STAIR" =========
# STAIR	CREATE	BuildingStorey	CREATE a STAIR in relation to the specified BuildingStorey
# STAIR	CREATE	Space	CREATE a STAIR in relation to the specified Space
# STAIR	CREATE	Element	CREATE a STAIR in relation to the specified Element (WALL)
# ------------------------------------------------------------------------------------------------------
# STAIR	MODIFY	BuildingStorey	MODIFY a STAIR in relation to the specified BuildingStorey
# STAIR	MODIFY	Space	MODIFY a STAIR in relation to the specified Space
# STAIR	MODIFY	Element	MODIFY a STAIR in relation to the specified Element (WALL)
# ------------------------------------------------------------------------------------------------------
# STAIR	SWAP	Element Family Type	SWAP a STAIR to another STAIR of a different Element Family Type
# STAIR	SWAP	Element Property	SWAP a STAIR to another STAIR with different Element Properties
# ------------------------------------------------------------------------------------------------------
# STAIR	DELETE	Element	DELETE a Element (STAIR)
# ------------------------------------------------------------------------------------------------------
class ComponentHandlerStair(ComponentHandlerBase):
    """
    Definition of the Class
    Handler class for stair related functions.
    """

    def __init__(self, doc, enable_group_handling=True):

        # Some links as Core References:
        # https://help.autodesk.com/view/RVT/2015/ENU/?guid=GUID-C60041FB-069E-4C89-BE67-A0593E790995
        # https://forum.dynamobim.com/t/stairs-disappearing-via-python/32952
        # https://forum.dynamobim.com/t/create-stairs-from-cad-link-list-of-lines-with-python-script/53999/9
        
        self.doc = doc
        self._get_sorted_levels(doc)
        self.enable_group_handling = enable_group_handling  # NEW: Control flag
    
    def _get_wall_center(self, wall):
        location = wall.Location
        if isinstance(location, LocationCurve):
            curve = location.Curve
            return curve.Evaluate(0.5, True)  # mid-point
        else:
            raise Exception("Wall does not have a LocationCurve.")
    
    def _calculate_stair_move_vector(
        self,
        reference_org_room,
        reference_new_room,
        reference_org_wall=None,
        reference_new_wall=None,
        location_index=2,
        ):
        
        if reference_org_wall and reference_new_wall:

            # use wall central point for move vector calculation.
            # this considers the condition that onely one partial segment of the wall is located within the room.
            self.room_bdry_edge = 0.0 # skip the non-central cases.
            pt_org = self._get_room_relevant_wall_placement_point(room=reference_org_room, wall=reference_org_wall, location_index=location_index)
            pt_new = self._get_room_relevant_wall_placement_point(room=reference_new_room, wall=reference_new_wall, location_index=location_index)
        
        else:
            # use room central point direct for move vector calculation.
            pt_org = reference_org_room.Location.Point
            pt_new = reference_new_room.Location.Point
        
        move_vector = pt_new.Subtract(pt_org)

        return move_vector
    
    # ==================== Group HELPER FUNCTIONS====================
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
                Output("[INFO-HandlerStair] Copied group: {} -> {}".format(gid.IntegerValue, copied_group_ids[0].IntegerValue))
            except Exception as ge:
                Output("[WARN-HandlerStair] Failed to copy group {}: {}".format(gid.IntegerValue, str(ge)))

        # Phase 2: Copy standalone elements
        if standalone_ids.Count > 0:
            try:
                copied_standalone_ids = ElementTransformUtils.CopyElements(self.doc, standalone_ids, move_vector)
                for cid in copied_standalone_ids:
                    all_new_ids.Add(cid)
                Output("[INFO-HandlerStair] Copied {} standalone elements.".format(standalone_ids.Count))
            except Exception as ee:
                Output("[WARN-HandlerStair] Failed to copy standalone elements: {}".format(str(ee)))
                
        return all_new_ids
    
    def _move_elements_group_aware(self, element_ids_to_move, move_vector):
        """Group-aware movement logic."""
        group_ids, standalone_ids = self._partition_targets_by_group(element_ids_to_move)
        
        if group_ids:
            Output("[INFO-HandlerStair] Found {} group(s) containing stair components.".format(len(group_ids)))
        if standalone_ids.Count > 0:
            Output("[INFO-HandlerStair] Found {} standalone element(s) to move.".format(standalone_ids.Count))

        # Phase 1: Move groups
        for gid in group_ids:
            ginst = self.doc.GetElement(gid)
            if ginst is None:
                continue
            try:
                if hasattr(ginst, "Pinned") and ginst.Pinned:
                    Output("[INFO-HandlerStair] Group {} is pinned. Skipping.".format(gid.IntegerValue))
                    continue
                ElementTransformUtils.MoveElement(self.doc, gid, move_vector)
                Output("[INFO-HandlerStair] Moved group: {}".format(gid.IntegerValue))
            except Exception as ge:
                Output("[WARN-HandlerStair] Failed to move group {}: {}".format(gid.IntegerValue, str(ge)))

        # Phase 2: Move standalone elements
        if standalone_ids.Count > 0:
            try:
                ElementTransformUtils.MoveElements(self.doc, standalone_ids, move_vector)
                Output("[INFO-HandlerStair] Moved {} standalone elements.".format(standalone_ids.Count))
            except Exception as ee:
                Output("[WARN-HandlerStair] Failed to move standalone elements: {}".format(str(ee)))

    def _get_group_id_or_invalid(self, el):
        """Return owning GroupId or InvalidElementId if none."""
        invalid = ElementId.InvalidElementId
        try:
            gid = el.GroupId  # many elements expose this
            return gid if gid and gid != invalid else invalid
        except:
            return invalid
    
    # ===============================================
    # NEW
    def stair_create(
        self,
        ref_stair_id,
        ref_org_room_id,
        ref_org_wall_id,
        ref_room_id,
        ref_wall_id,
        params_stair_create=1,
        use_group_handling=None):

        """
        # STAIR	CREATE	BuildingStorey	    CREATE a STAIR in relation to the specified BuildingStorey
        # STAIR	CREATE	Space	            CREATE a STAIR in relation to the specified Space
        # STAIR	CREATE	Element	            CREATE a STAIR in relation to the specified Element (WALL)
        
        Parameters:
            ref_stair_id (ElementId or int): ID of the stair to copy.
            ref_org_room_id (ElementId or int): ID of the room containing the original stair.
            ref_org_wall_id (ElementId or int or None): Wall near original stair (used to refine movement).
            ref_room_id (ElementId or int): ID of the target room where the stair will be placed.
            ref_wall_id (ElementId or int or None): Target wall near new stair location.
            # TODO: refine the function by fix the wall reference issue, by using the parameter 'params_stair_create'
            params_stair_create (int).
        """

        group_handling_active = (use_group_handling if use_group_handling is not None 
                                 else self.enable_group_handling)
        
        # compulsory input part
        if isinstance(ref_stair_id, int):
            ref_stair_id = ElementId(ref_stair_id)
        if isinstance(ref_org_room_id, int):
            ref_org_room_id = ElementId(ref_org_room_id)
        if isinstance(ref_room_id, int):
            ref_room_id = ElementId(ref_room_id)
        ref_stair = self.doc.GetElement(ref_stair_id)
        org_room = self.doc.GetElement(ref_org_room_id)
        new_room = self.doc.GetElement(ref_room_id)

        # optional input part
        if isinstance(ref_org_wall_id, int):
            ref_org_wall_id = ElementId(ref_org_wall_id)
        if isinstance(ref_wall_id, int):
            ref_wall_id = ElementId(ref_wall_id)
        org_wall = self.doc.GetElement(ref_org_wall_id) if ref_org_wall_id else None
        new_wall = self.doc.GetElement(ref_wall_id) if ref_wall_id else None

        # Safety check
        if not ref_stair or not org_room or not new_room:
            Output("[ERROR-HandlerStair] Invalid input elements. Please check the provided IDs for stair, original room, and new room.")
            return None

        # Creation by copying.
        try:

            move_vector = self._calculate_stair_move_vector(
                reference_org_room=org_room, reference_new_room=new_room,
                reference_org_wall=org_wall, reference_new_wall=new_wall)
            Output("[INFO-HandlerStair] Move vector calculated")

            # ==================== NEW: COLLECT STAIR COMPONENTS ====================
            # Collect all subcomponents of the stair (run, landing, supports)
            element_ids_to_copy = List[ElementId]()
            run_ids = ref_stair.GetStairsRuns()
            landing_ids = ref_stair.GetStairsLandings()
            support_ids = ref_stair.GetStairsSupports()

            # Add main stair ID
            if ref_stair_id:
                element_ids_to_copy.Add(ref_stair_id)

            # Add subcomponent IDs safely
            for eid in run_ids:
                if eid:
                    element_ids_to_copy.Add(eid)
            for eid in landing_ids:
                if eid:
                    element_ids_to_copy.Add(eid)
            for eid in support_ids:
                if eid:
                    element_ids_to_copy.Add(eid)
            # ====================================================================

            t = Transaction(self.doc, "Duplicate Stair from Room A to Room B")

            # ====== failure processor ======== [good]
            options = t.GetFailureHandlingOptions()
            options.SetFailuresPreprocessor(NoWarningsFailurePreprocessor())
            t.SetFailureHandlingOptions(options)

            t.Start()
            # ==================== MODULAR COPY LOGIC ====================
            if group_handling_active:
                Output("[INFO-HandlerStair] Using group-aware copying.")
                all_new_ids = self._copy_elements_group_aware(element_ids_to_copy, move_vector)
            else:
                Output("[INFO-HandlerStair] Using simple copying.")
                all_new_ids = ElementTransformUtils.CopyElement(self.doc, ref_stair.Id, move_vector)
            # ============================================================
            t.Commit()

            # ==================== NEW: FIND THE CREATED STAIR FROM COPIED ELEMENTS ====================
            created_stair = None
            # Find the main stair among the copied elements
            for new_id in all_new_ids:
                new_element = self.doc.GetElement(new_id)
                if new_element and hasattr(new_element, 'GetStairsRuns'):  # This identifies it as a stair
                    created_stair = new_id
                    break
            
            if not created_stair and all_new_ids.Count > 0:
                # Fallback: use first copied element (might be the stair or part of it)
                created_stair = all_new_ids[0]
            
            if created_stair:
                Output("[INFO-HandlerStair] Stair duplicated successfully: {}".format(str(created_stair.IntegerValue)))
            else:
                Output("[WARN-HandlerStair] Stair copied but main stair element not clearly identified.")
                created_stair = all_new_ids[0] if all_new_ids.Count > 0 else None
            # ==========================================================================================
            
            # ---------------------- create opening in slab below(lower) / above(upper) stair ----------------------
            if created_stair:
                slab_handler = ComponentHandlerSlab(self.doc)
                slab_handler.slab_modify(created_stair, ref_room_id)
                Output("[INFO-HandlerStair] Slab modification has been executed after 'stair_create'.")

            return created_stair
        
        except Exception as e:
            Output("[ERROR-HandlerStair] Failed to duplicate stair: {}".format(e))
            if t.HasStarted():
                t.RollBack()
            return None
    # NEW
    # ===============================================


    def _print_curve_geometry_info(self, label, curve_list):

        print("\n--- {} ---".format(label))
        for i, curve in enumerate(curve_list):
            start = curve.GetEndPoint(0)
            end = curve.GetEndPoint(1)
            print("Curve {:2d}: Start({:.2f}, {:.2f}, {:.2f}) -> End({:.2f}, {:.2f}, {:.2f})".format(
                i,
                start.X, start.Y, start.Z,
                end.X, end.Y, end.Z
            ))

    def _create_stair_by_levels_curves(self, bottom_top_level_ids, stair_curves):
    
        stair_curve_brdy, stair_curve_rise, stair_curve_path = stair_curves
        stair_curve_brdy = convert_python_to_curve_list(stair_curve_brdy)
        stair_curve_rise = convert_python_to_curve_list(stair_curve_rise)
        stair_curve_path = convert_python_to_curve_list(stair_curve_path)
        
        # -------------------------------------
        # Step 1: Force-close all transactions (safe-guard)
        print("[DEBUG] Forcing close of all active transactions...")
        TransactionManager.Instance.ForceCloseTransaction()
        
        # -------------------------------------
        # Step 2: Check if doc is modifiable
        if self.doc.IsModifiable:
            print("[ERROR] Document is currently modifiable. Cannot start StairsEditScope.")
            return

        # -------------------------------------
        # Step 3: start stairs scope
        # NOTE for 'StairsEditScope': 
        # StairsEditScope is not permitted to start at this moment for one of the following possible reasons:
        # The document is in read-only state, or the document is currently modifiable, 
        # or there already is another edit mode active in the document.
        try:
            print("[DEBUG] Starting StairsEditScope...")
            stair_scope = StairsEditScope(self.doc, "Sketched Stair")
            stair_id = stair_scope.Start(bottom_top_level_ids[0], bottom_top_level_ids[1])
            stair_based_elevation = self.doc.GetElement(bottom_top_level_ids[0]).Elevation
            
        except Exception as e:
            print("[ERROR] Failed to start StairsEditScope:", e)
            return

        # -------------------------------------
        # Step 4: Normal transaction to place stair run
        __title__ = "Create Sketched Stair"
        t = Transaction(self.doc, __title__)
        t.Start()
        
        try:
            # Create the run
            run = StairsRun.CreateSketchedRun(
                self.doc,
                stair_id,
                stair_based_elevation,
                stair_curve_brdy,
                stair_curve_rise,
                stair_curve_path
            )
            t.Commit()

            # --- Commit the stair edit scope ---
            try:
                stair_scope.Commit(NoWarningsFailurePreprocessor())
            except Exception as e:
                print("[WARNING] Commit error:")
                for line in traceback.format_exc().splitlines():
                    print(line)

        except Exception as e:
            print("[ERROR] During stair creation:", e)
            for line in traceback.format_exc().splitlines():
                print(line)
            t.RollBack()
            run = None
        
        finally:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            print("[INFO] Stair creation process finished.")
            return run

    # ===============================================
    # NEW
    def stair_modify(
        self,
        ref_stair_id,
        ref_org_room_id,
        ref_org_wall_id,
        ref_room_id,
        ref_wall_id,
        params_stair_modify=1, 
        use_group_handling=None):
        """
        # STAIR	MODIFY	BuildingStorey	        MODIFY a STAIR in relation to the specified BuildingStorey
        # STAIR	MODIFY	Space	                MODIFY a STAIR in relation to the specified Space
        # STAIR	MODIFY	Element	                MODIFY a STAIR in relation to the specified Element (WALL)

        Parameters:
            ref_stair_id (ElementId or int): ID of the stair to move.
            ref_org_room_id (ElementId or int): ID of the room containing the original stair.
            ref_org_wall_id (ElementId or int or None): Wall near original stair.
            ref_room_id (ElementId or int): ID of the target room where the stair will be placed.
            ref_wall_id (ElementId or int or None): Target wall near new stair location.
            # TODO: refine the function by fix the wall reference issue, by using the parameter 'params_stair_modify'
            params_stair_modify (int).
        """
        # Determine if group handling should be used
        group_handling_active = (use_group_handling if use_group_handling is not None 
                               else self.enable_group_handling)

        # compulsory input part
        if isinstance(ref_stair_id, int):
            ref_stair_id = ElementId(ref_stair_id)
        if isinstance(ref_org_room_id, int):
            ref_org_room_id = ElementId(ref_org_room_id)
        if isinstance(ref_room_id, int):
            ref_room_id = ElementId(ref_room_id)
        ref_stair = self.doc.GetElement(ref_stair_id)
        org_room = self.doc.GetElement(ref_org_room_id)
        new_room = self.doc.GetElement(ref_room_id)

        # optional input part
        if isinstance(ref_org_wall_id, int):
            ref_org_wall_id = ElementId(ref_org_wall_id)
        if isinstance(ref_wall_id, int):
            ref_wall_id = ElementId(ref_wall_id)
        org_wall = self.doc.GetElement(ref_org_wall_id) if ref_org_wall_id else None
        new_wall = self.doc.GetElement(ref_wall_id) if ref_wall_id else None

        # Safety check
        if not ref_stair or not org_room or not new_room:
            Output("[ERROR-HandlerStair] Invalid input elements. Please check the provided IDs of stair, original room, and new room.")
            return None

        # Creation by moving.
        try:
            t = Transaction(self.doc, "Move Stair to New Room")

            move_vector = self._calculate_stair_move_vector(
                reference_org_room=org_room, reference_new_room=new_room,
                reference_org_wall=org_wall, reference_new_wall=new_wall)
            Output("[INFO-HandlerStair] Move vector calculated.")

            # Collect all subcomponents of the stair (run, landing, supports)
            element_ids_to_move = List[ElementId]()  # Start with empty .NET list
            run_ids = ref_stair.GetStairsRuns()
            landing_ids = ref_stair.GetStairsLandings()
            support_ids = ref_stair.GetStairsSupports()

            # Add main stair ID
            if ref_stair_id:
                element_ids_to_move.Add(ref_stair_id)

            # Add subcomponent IDs safely
            for eid in run_ids:
                if eid:
                    element_ids_to_move.Add(eid)
            for eid in landing_ids:
                if eid:
                    element_ids_to_move.Add(eid)
            for eid in support_ids:
                if eid:
                    element_ids_to_move.Add(eid)
            
            # Setup failure processor
            options = t.GetFailureHandlingOptions()
            options.SetFailuresPreprocessor(NoWarningsFailurePreprocessor())
            t.SetFailureHandlingOptions(options)

            t.Start()
            # ==================== MODULAR MOVEMENT LOGIC ====================
            if group_handling_active:
                Output("[INFO-HandlerStair] Using group-aware movement.")
                self._move_elements_group_aware(element_ids_to_move, move_vector)
            else:
                Output("[INFO-HandlerStair] Using simple movement.")
                ElementTransformUtils.MoveElements(self.doc, element_ids_to_move, move_vector)
            # ================================================================
            t.Commit()

            modified_stair = ref_stair_id
            Output("[INFO-HandlerStair] Stair modified successfully.".format(str(modified_stair.IntegerValue)))
            
            # ---------------------- create opening in slab below(lower) / above(upper) stair ----------------------
            slab_handler = ComponentHandlerSlab(self.doc)
            slab_handler.slab_modify(modified_stair, ref_room_id)
            Output("[INFO-HandlerStair] Slab modification has been executed after 'stair_modify'.")

            Output("[INFO-HandlerStair] Stair moved successfully to new room.")
            return ref_stair

        except Exception as e:
            
            Output("[ERROR-HandlerStair] Failed to move stair: {}".format(e))
            if t.HasStarted():
                t.RollBack()
            return None
    # NEW 
    # ===============================================

    # ================================================
    # ================================================
    # ================================================
    # ================  D E L E T E  =================
    # ================================================
    # ================================================
    # ================================================
    def stair_delete(self, ref_stair_id):
        """
       # STAIR	DELETE	Element	DELETE a Element (STAIR)
        """
        if isinstance(ref_stair_id, int):
            ref_stair_id = ElementId(ref_stair_id)
        stair = self.doc.GetElement(ref_stair_id)
        if not stair:
            Output("[ERROR-HandlerStair] Stair ID not valid.")
            return None

        t = Transaction(self.doc, "Delete Stair")
        t.Start()
        try:
            self.doc.Delete(stair.Id)
            t.Commit()
            Output("[INFO-HandlerStair] Stair deleted successfully.")
            return True
        except Exception as e:
            Output("[ERROR-HandlerStair] Failed to delete stair: {}".format(e))
            if t.HasStarted():
                t.RollBack()
            return None
        
    # ==============================================================================================
    # SAVE FOR MORE ADVANCED STAIR CREATION IN THE FUTURE
    # def _get_stair_creation_parameters(self, ref_room_id, shape="I"):
    #     """
    #     Create stairs from sketched geometry using Revit API with structured transaction logic.
    #     """

    #     if shape != "I":
    #         # first only focus on I shape when creating (not copying/duplicating.)
    #         print("Please check if this stair shape has been implemented.")
    #         return None
            
    #     self._get_overall_geo_values()

    #     stair_bottom_level_id, stair_top_level_id, stair_location_ori_point = self._get_stair_point_from_room(ref_room_id)
        
    #     bottom_top_level_ids = [stair_bottom_level_id, stair_top_level_id]
        
    #     stair_curves = self._get_stair_curves_I_shape(stair_location_ori_point)

    #     return bottom_top_level_ids, stair_curves

    # def _get_stair_point_from_room(self, room):
    #     """
    #     Create stairs between two levels using Revit API (pyRevit compatible).
    #     """
        
    #     if isinstance(room, ElementId):
    #         room = self.doc.GetElement(room)

    #     stair_bottom_level_id = None
    #     stair_top_level_id = None 
        
    #     stair_location_ori_point = None

    #     stair_bottom_level_id = room.LevelId
    #     level_above = self._find_level_above_room(room)
    #     stair_top_level_id = ElementId(int(level_above))
        
    #     stair_location_ori_point = room.Location.Point

    #     return (stair_bottom_level_id, stair_top_level_id, stair_location_ori_point)

    # def _get_stair_curves_I_shape(
    #     self, stair_ori_point, offset_x=4, offset_y=4, riser_num=20, verbose=False):
    #     """
    #     Generates boundary, riser, and path curves for stair creation.
    #     The number of risers is dynamically calculated based on level elevation difference.
    #     """

    #     print ('riser_num:{}'.format(riser_num))
    #     stair_curve_brdy, stair_curve_rise, stair_curve_path = [], [], []

    #     # ----------------------------
    #     # Define stair boundary corners
    #     pnt1 = XYZ(stair_ori_point.X - offset_x, stair_ori_point.Y - offset_y, stair_ori_point.Z)
    #     pnt2 = XYZ(stair_ori_point.X + offset_x, stair_ori_point.Y - offset_y, stair_ori_point.Z)
    #     pnt3 = XYZ(stair_ori_point.X - offset_x, stair_ori_point.Y + offset_y, stair_ori_point.Z)
    #     pnt4 = XYZ(stair_ori_point.X + offset_x, stair_ori_point.Y + offset_y, stair_ori_point.Z)

    #     # ----------------------------
    #     # Boundary curves (left and right sides)
    #     stair_curve_brdy = [Line.CreateBound(pnt1, pnt2), Line.CreateBound(pnt3, pnt4)]

    #     # ----------------------------
    #     # Riser curves
    #     stair_curve_rise = []
    #     for i in range(riser_num+1):
    #         t = i / float(riser_num)
    #         vec_rise1 = pnt2.Subtract(pnt1).Multiply(t)
    #         vec_rise2 = pnt4.Subtract(pnt3).Multiply(t)
    #         start = pnt1.Add(vec_rise1)
    #         end = pnt3.Add(vec_rise2)
    #         stair_curve_rise.append(Line.CreateBound(start, end))

    #     # ----------------------------
    #     # Path curve
    #     path_start = pnt1.Add(pnt3).Divide(2.0)
    #     path_end = pnt2.Add(pnt4).Divide(2.0)
    #     stair_curve_path = [Line.CreateBound(path_start, path_end)]

    #     # ----------------------------
    #     # Optional print
    #     if verbose:
    #         self._print_curve_geometry_info("Boundary Curves", stair_curve_brdy)
    #         self._print_curve_geometry_info("Riser Curves", stair_curve_rise)
    #         self._print_curve_geometry_info("Path Curves", stair_curve_path)
        
    #     return [stair_curve_brdy, stair_curve_rise, stair_curve_path]
    
    # def _create_stair_from_room_to_room(
    #     self,
    #     stair_id,
    #     room_ori_id,
    #     room_new_id):
    #     """
    #     Copies a stair from room_ori's center to room_new's center.
    #     Only works if stair has point-based Location.
    #     """

    #     if isinstance(stair_id, int):
    #         stair_id = ElementId(stair_id)
    #     if isinstance(room_ori_id, int):
    #         room_ori_id = ElementId(room_ori_id)
    #     if isinstance(room_new_id, int):
    #         room_new_id = ElementId(room_new_id)
            
    #     stair = self.doc.GetElement(stair_id)
    #     room_ori = self.doc.GetElement(room_ori_id)
    #     room_new = self.doc.GetElement(room_new_id)
    
    #     pt_ori = room_ori.Location.Point
    #     pt_new = room_new.Location.Point
    #     move_vector = pt_new.Subtract(pt_ori)

    #     t = Transaction(self.doc, "Place a Stair by copying from an existing one")
        
    #     # Set the failure processor to handle warnings.
    #     options = t.GetFailureHandlingOptions()
    #     options.SetFailuresPreprocessor(NoWarningsFailurePreprocessor())
    #     t.SetFailureHandlingOptions(options)

    #     t.Start()
    #     try:
    #         new_ids = ElementTransformUtils.CopyElement(self.doc, stair.Id, move_vector)
    #         t.Commit()
    #         print("[INFO] Stair copied from Room A to Room B.")
    #         return new_ids[0]
    #     except Exception as e:
    #         print("[ERROR] Failed to copy stair: {}".format(e))
    #         t.RollBack()

    # # ---------------------------------------------
    # # SAVE for stair creation by selecting a C-shape
    # # ---------------------------------------------
    # # TODO: For now we first skip the curve shape stairway..... let's see if we have enough time to handle this.
    # def _get_stair_curves_C_shape(self, riser_num=15, radius=4.0, total_angle_deg=270, verbose=True):
    #     """
    #     Generate circular stair sketch curves (boundary, risers, path) for Revit stairs.
    #     Curves remain in a horizontal plane (Z = constant).
    #     """
        
    #     self.stair_curve_brdy = []
    #     self.stair_curve_rise = []
    #     self.stair_curve_path = []

    #     c_point = self.stair_ori_point
    #     angle_step = radians(total_angle_deg) / float(riser_num)

    #     # riser curves (on same Z)
    #     for i in range(riser_num):
    #         theta0 = angle_step * i
    #         theta1 = angle_step * (i + 1)

    #         x0 = c_point.X + radius * cos(theta0)
    #         y0 = c_point.Y + radius * sin(theta0)
    #         x1 = c_point.X + radius * cos(theta1)
    #         y1 = c_point.Y + radius * sin(theta1)

    #         p0 = XYZ(x0, y0, c_point.Z)
    #         p1 = XYZ(x1, y1, c_point.Z)

    #         self.stair_curve_rise.append(Line.CreateBound(p0, p1))

    #     # boundary curves: approximate outer boundary lines
    #     self.stair_curve_brdy = [
    #         Line.CreateBound(self.stair_curve_rise[0].GetEndPoint(0), self.stair_curve_rise[-1].GetEndPoint(0)),
    #         Line.CreateBound(self.stair_curve_rise[0].GetEndPoint(1), self.stair_curve_rise[-1].GetEndPoint(1))
    #     ]
        
    #     # path curve: from midpoint to midpoint of each riser
    #     midpoints = [curve.Evaluate(0.5, True) for curve in self.stair_curve_rise]
    #     self.stair_curve_path = []
    #     for i in range(len(midpoints) - 1):
    #         self.stair_curve_path.append(Line.CreateBound(midpoints[i], midpoints[i + 1]))
        
    #     if verbose:
    #         self._print_curve_geometry_info("Circular Boundary Curves", self.stair_curve_brdy)
    #         self._print_curve_geometry_info("Circular Riser Curves", self.stair_curve_rise)
    #         self._print_curve_geometry_info("Circular Path Curve", self.stair_curve_path)
    
    # # ---------------------------------------------
    # # SAVE for stair creation by selecting a U-shape
    # # ---------------------------------------------
    # # TODO: For now we first skip the U shape stairway..... let's see if we have enough time to handle this.
    # def create_stairs_within_room_Ushape(self, room):
    #     """
    #     Create U-shaped stairs from sketched geometry using Revit API.
    #     """
    #     self._get_stair_point_from_room(room)
    #     self._get_stair_curves_from_point()

    #     # ---------------------------------------------
    #     # Step 1: Force close any auto transaction
    #     TransactionManager.Instance.ForceCloseTransaction()

    #     # Step 2: Check modifiable state
    #     if self.doc.IsModifiable:
    #         print("[ERROR] Document is currently modifiable. Cannot start StairsEditScope.")
    #         return
        
    #     # Step 3: Prepare stairs elevation info
    #     level_bottom = self.doc.GetElement(self.level_id_stair_bottom)
    #     level_top = self.doc.GetElement(self.level_id_stair_top)
    #     stair_based_elevation = level_bottom.Elevation
    #     stair_top_elevation = level_top.Elevation
    #     stair_height = stair_top_elevation - stair_based_elevation
        
    #     try:
    #         # Step 4: Start StairsEditScope before Transaction
    #         stair_scope = StairsEditScope(self.doc, "U-Shape Stair")
    #         stair_id = stair_scope.Start(self.level_id_stair_bottom, self.level_id_stair_top)

    #         # NOTE for 'StairsEditScope': 
    #         # StairsEditScope is not permitted to start at this moment for one of the following possible reasons:
    #         # The document is in read-only state,
    #         # or the document is currently modifiable,
    #         # or there already is another edit mode active in the document.
        
    #     except Exception as e:
    #         print("[ERROR] Failed to start StairsEditScope:", e)
    #         return
        
    #     __title__ = "Create Sketched Stair"
    #     t = Transaction(self.doc, __title__)
    #     t.Start()
        
    #     try:
    #         # --- Run 1 ---
    #         run1 = StairsRun.CreateSketchedRun(
    #             self.doc,
    #             stair_id,
    #             stair_based_elevation,
    #             self.stair_curve_brdy,
    #             self.stair_curve_rise,
    #             self.stair_curve_path
    #         )

    #         # --- Landing ---
    #         c_point = self.stair_ori_point
    #         z_landing = stair_based_elevation + stair_height / 2
    #         loop = CurveLoop()
    #         x1, x2 = c_point.X + 7.5, c_point.X + 12.5
    #         y1, y2 = c_point.Y + 5.0, c_point.Y - 5.0
    #         loop.Append(Line.CreateBound(XYZ(x1, y1, z_landing), XYZ(x2, y1, z_landing)))
    #         loop.Append(Line.CreateBound(XYZ(x2, y1, z_landing), XYZ(x2, y2, z_landing)))
    #         loop.Append(Line.CreateBound(XYZ(x2, y2, z_landing), XYZ(x1, y2, z_landing)))
    #         loop.Append(Line.CreateBound(XYZ(x1, y2, z_landing), XYZ(x1, y1, z_landing)))
    #         landing = StairsLanding.CreateSketchedLanding(self.doc, stair_id, loop, z_landing)

    #         # # --- Run 2 ---
    #         # run2_line = Line.CreateBound(
    #         #     XYZ(x2 - 2.5, y2, z_landing),
    #         #     XYZ(x2 - 2.5, y2 - 10, stair_top_elevation)
    #         # )
    #         # run2 = StairsRun.CreateStraightRun(self.doc, stair_id, run2_line, StairsRunJustification.Center)
    #         # run2.ActualRunWidth = 10

    #         # --- Finalize ---
    #         t.Commit()
    #         stair_scope.Commit(NoWarningsFailurePreprocessor())
    #         print("[SUCCESS] Stair with landing created.")
    #         return [run1, landing]

    #     except Exception as e:
    #         print("[ERROR] During stair creation:", e)
    #         t.RollBack()
    #     finally:
    #         print("[INFO] Stair creation process complete.")

    # # ---------------------------------------------
    # # SAVE for stair creation by selecting a U-shape
    # # ---------------------------------------------
    # # a fundamental function to create a door on the wall, without any limitation on room projection.
    # def create_door_on_wall(
    #     self,
    #     wall,
    #     door_type=None,
    #     level=None):
    #     """
    #     Places a door at the midpoint of a wall.
    #     """

    #     if not door_type:
    #         door_type = FilteredElementCollector(self.doc)\
    #             .OfCategory(BuiltInCategory.OST_Doors)\
    #             .WhereElementIsElementType()\
    #             .FirstElement()

    #     if not level:
    #         level = self.doc.GetElement(wall.LevelId)

    #     location_curve = wall.Location.Curve
    #     placement_point = location_curve.Evaluate(0.5, True) # hereby a 0.5 is sleected to place the door in the middle of the wall.
        
    #     if not door_type.IsActive:
    #         t = Transaction(self.doc, "Activate Door Type")
    #         t.Start()
    #         door_type.Activate()
    #         t.Commit()

    #     t = Transaction(self.doc, "Insert Door")
    #     t.Start()
    #     try:
    #         door = self.doc.Create.NewFamilyInstance(
    #             placement_point, door_type, wall, level, Structure.StructuralType.NonStructural)
    #         t.Commit()
    #         print("[INFO] Door created successfully.")
    #         return door
    #     except Exception as e:
    #         print("[ERROR] Failed to place door:", e)
    #         t.RollBack()

    
    # ================================================
    # ================================================
    # IMPORTANT: previous WORKING CODEs that works.
    # ================================================
    # ================================================
    # def stair_creation_within_room(self, room, shape="I"):
    #     """
    #     Create stairs from sketched geometry using Revit API with structured transaction logic.
    #     """

    #     # Core Reference:
    #     # https://help.autodesk.com/view/RVT/2015/ENU/?guid=GUID-C60041FB-069E-4C89-BE67-A0593E790995
    #     # https://forum.dynamobim.com/t/stairs-disappearing-via-python/32952
    #     # https://forum.dynamobim.com/t/create-stairs-from-cad-link-list-of-lines-with-python-script/53999/9
        
    #     self._get_overall_geo_values()
    #     self._get_stair_point_from_room(room)
    
    #     if shape == "I":
    #         self._get_stair_curves_I_shape()
    #     elif shape == "C":
    #         print("Warning: Circular stair creation is not yet properly implemented Jiabin.")
    #         # self._get_stair_curves_C_shape()
    #     else:
    #         print("Please check if this stair shape has been implemented.")
    #         return None
        
    #     # -------------------------------------
    #     # Step 1: Force-close all transactions (safe-guard)
    #     print("[DEBUG] Forcing close of all active transactions...")
    #     TransactionManager.Instance.ForceCloseTransaction()
        
    #     # -------------------------------------
    #     # Step 2: Check if doc is modifiable
    #     if self.doc.IsModifiable:
    #         print("[ERROR] Document is currently modifiable. Cannot start StairsEditScope.")
    #         return

    #     # -------------------------------------
    #     # Step 3: start stairs scope
    #     try:
    #         # Start stair scope
    #         # NOTE for 'StairsEditScope': 
    #         # StairsEditScope is not permitted to start at this moment for one of the following possible reasons:
    #         # The document is in read-only state, or the document is currently modifiable, or there already is another edit mode active in the document.
    #         print("[DEBUG] Starting StairsEditScope...")
    #         stair_scope = StairsEditScope(self.doc, "Sketched Stair")
    #         stair_id = stair_scope.Start(self.level_id_stair_bottom, self.level_id_stair_top)
    #         stair_based_elevation = self.doc.GetElement(self.level_id_stair_bottom).Elevation
            
    #     except Exception as e:
    #         print("[ERROR] Failed to start StairsEditScope:", e)
    #         return
        
    #     # -------------------------------------
    #     # Step 4: Normal transaction to place stair run
    #     __title__ = "Create Sketched Stair"
    #     t = Transaction(self.doc, __title__)
    #     t.Start()
        
    #     try:
    #         # Create the run
    #         run = StairsRun.CreateSketchedRun(
    #             self.doc,
    #             stair_id,
    #             stair_based_elevation,
    #             self.stair_curve_brdy,
    #             self.stair_curve_rise,
    #             self.stair_curve_path
    #         )
            
    #         t.Commit()
    #         stair_scope.Commit(NoWarningsFailurePreprocessor())
    #         print("Stair creation succeeded.")
    #         return run
        
    #     except Exception as e:

    #         print("Error during stair creation:", e)
    #         t.RollBack()

    #     finally:
            
    #         if t.HasStarted() and not t.HasEnded():
    #             t.RollBack() 
    #         print("Stair creation process finished.")
    