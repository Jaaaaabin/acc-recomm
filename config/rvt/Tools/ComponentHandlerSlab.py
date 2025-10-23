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
from System.Collections.Generic import *
from Autodesk.Revit.DB import ElementId, XYZ, Line, Transaction, SketchEditScope

# IMPORT - CUSTOM FUNCTIONS. 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#
from Tools.ComponentHandlerBase import NoWarningsFailurePreprocessor, ComponentHandlerBase

# FUNCTIONS 
# =====================================================================================================
# =====================================================================================================
# ====================================================================================================

# CLASS - ComponentHandlerSlab (Subclass)
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class ComponentHandlerSlab(ComponentHandlerBase):
    """
    Definition of the Class
    Handler class for slab related functions.
    main functions:
    slab_cutting_by_stair:      Explanation.... 
    """

    def __init__(self, doc):
        
        self.doc = doc
        self._get_sorted_levels(doc)
    
    def slab_modify(self, ref_stair_id, ref_room_id):
        """
        SLAB - MODIFY.
        """
        
        room, stair = self._get_room_and_stair(ref_room_id, ref_stair_id)
        if not room or not stair:
            Output("[ERROR-HandlerSlab] Room or Stair not found. Cannot proceed with slab modification.")
            return
        
        related_level, related_floor, bbx_stair = self._get_related_floor_and_bbox(room, stair)
        if not related_floor or not bbx_stair:
            Output("[ERROR-HandlerSlab] Could not find related floor or bounding box for the stair.")
            return
        
        Output("[INFO-HandlerSlab] Related floor and bounding box retrieved successfully.")

        Output("[INFO-HandlerSlab] Details -  Related Level: {}, Floor: {}, Bounding Box: {}".format(
            related_level.Id,
            related_floor.Id,
            bbx_stair))
        
        self._create_opening_in_floor(related_floor, related_level, bbx_stair)

    def _get_room_and_stair(self, ref_room_id, ref_stair_id):

        if isinstance(ref_stair_id, int):
            ref_stair_id = ElementId(ref_stair_id)
        if isinstance(ref_room_id, int):
            ref_room_id = ElementId(ref_room_id)

        room = self.doc.GetElement(ref_room_id)
        if not room:
            Output("[ERROR-HandlerSlab] Room not found.")
            return None, None

        stair = self.doc.GetElement(ref_stair_id)
        if not stair:
            Output("[ERROR-HandlerSlab] Stair not found.")
            return None, None

        return room, stair
    
    def _get_related_floor_and_bbox(self, room, stair, pos_floor='lower'):
        
        if pos_floor == 'upper':
            related_level = self._find_level_above_room(room)
            related_level = self.doc.GetElement(ElementId(int(related_level)))

        elif pos_floor == 'lower':
            # BUG: issue here
            related_level = room.Level # the Level is already the element.
            # related_level = self.doc.GetElement(ElementId(int(related_level)))

        else:
            raise ValueError("Invalid position for floor. Use 'upper' or 'lower'.")
        
        related_floor = self._find_floor_closest_to_level(related_level)
        bbx_stair = stair.get_BoundingBox(None)
        
        return related_level, related_floor, bbx_stair
    

    def _create_opening_in_floor(self, floor_above, level_above, bbx_stair):
    
        sketch = self.doc.GetElement(floor_above.SketchId)
        sketchElevation = level_above.ProjectElevation

        # --- params/tolerances ---
        TOL = 1e-6
        INSET = 0.005  # 5 mm inset to avoid coincident-with-slab edges; tune if needed

        # Precompute, guard zero-area
        minX, minY = bbx_stair.Min.X, bbx_stair.Min.Y
        maxX, maxY = bbx_stair.Max.X, bbx_stair.Max.Y
        if (maxX - minX) < TOL or (maxY - minY) < TOL:
            Output("[ERROR-HandlerSlab] Stair bbox is degenerate; skip opening.")
            return None

        # Apply a small inset to reduce touching/overlap failures
        minX += INSET; minY += INSET
        maxX -= INSET; maxY -= INSET
        if (maxX - minX) < TOL or (maxY - minY) < TOL:
            Output("[ERROR-HandlerSlab] Inset collapsed opening profile; skip.")
            return None

        z = sketchElevation

        sketchEditScope = None
        t = None
        try:
            sketchEditScope = SketchEditScope(self.doc, "Add Opening Above the Target Stair")
            sketchEditScope.Start(sketch.Id)

            t = Transaction(self.doc, "Sketch Opening")
            options = t.GetFailureHandlingOptions()
            options.SetFailuresPreprocessor(NoWarningsFailurePreprocessor())
            t.SetFailureHandlingOptions(options)

            t.Start()

            curveArr = [
                Line.CreateBound(XYZ(minX, minY, z), XYZ(maxX, minY, z)),
                Line.CreateBound(XYZ(maxX, minY, z), XYZ(maxX, maxY, z)),
                Line.CreateBound(XYZ(maxX, maxY, z), XYZ(minX, maxY, z)),
                Line.CreateBound(XYZ(minX, maxY, z), XYZ(minX, minY, z)),
            ]

            # Ensure all curves lie on the sketch plane (paranoia; Z already set)
            sp = sketch.SketchPlane
            for c in curveArr:
                self.doc.Create.NewModelCurve(c, sp)

            # Commit the sketch edits first, then the edit scope
            t.Commit()

            # If Commit() throws (no resolution), we catch below
            sketchEditScope.Commit(NoWarningsFailurePreprocessor())

            Output("[INFO-HandlerSlab] Slab opening created successfully above or below the stair.")
            return True

        except Exception as e:
            Output("[ERROR-HandlerSlab] Slab opening creation failed: {0}".format(e))
            for line in traceback.format_exc().splitlines():
                Output(line)

            # Roll back the inner transaction if it started
            try:
                if t is not None and t.HasStarted():
                    t.RollBack()
            except Exception as _:
                pass

            # IMPORTANT: cancel the edit scope if it started
            try:
                if sketchEditScope is not None:
                    sketchEditScope.Cancel()
            except Exception as _:
                pass

            return None

    # # SAVE - OLD that somehow works
    # def _create_opening_in_floor(self, floor_above, level_above, bbx_stair):

    #     sketch = self.doc.GetElement(floor_above.SketchId)
    #     sketchElevation = level_above.ProjectElevation

    #     try:
            
    #         sketchEditScope = SketchEditScope(self.doc, "Add Opening Above the Target Stair")
    #         sketchEditScope.Start(sketch.Id)

    #         t = Transaction(self.doc, "Sketch Opening")

    #         options = t.GetFailureHandlingOptions()
    #         options.SetFailuresPreprocessor(NoWarningsFailurePreprocessor())
    #         t.SetFailureHandlingOptions(options)
            
    #         t.Start()
    #         minX, minY = bbx_stair.Min.X, bbx_stair.Min.Y
    #         maxX, maxY = bbx_stair.Max.X, bbx_stair.Max.Y
    #         z = sketchElevation

    #         curveArr = [
    #             Line.CreateBound(XYZ(minX, minY, z), XYZ(maxX, minY, z)),
    #             Line.CreateBound(XYZ(maxX, minY, z), XYZ(maxX, maxY, z)),
    #             Line.CreateBound(XYZ(maxX, maxY, z), XYZ(minX, maxY, z)),
    #             Line.CreateBound(XYZ(minX, maxY, z), XYZ(minX, minY, z)),
    #         ]

    #         for curve in curveArr:
    #             self.doc.Create.NewModelCurve(curve, sketch.SketchPlane)

    #         t.Commit()
    #         sketchEditScope.Commit(NoWarningsFailurePreprocessor())
    #         Output("[INFO-HandlerSlab] Slab opening created successfully above or below the stair.")

    #     except Exception as e:
            
    #         Output("[ERROR-HandlerSlab] Slab opening creation failed:", e)
    #         for line in traceback.format_exc().splitlines():
    #             Output(line)
    #         if t.HasStarted():
    #             t.RollBack()
    #         return None

    # def slab_modification(self, ref_stair_id, ref_room_id):
    #     """
    #     SLAB - MODIFY.
    #     """

    #     # -------------------------------------
    #     # Step 1: Get the Room and Stair Elements
        
    #     if isinstance(ref_stair_id, int):
    #         ref_stair_id = ElementId(ref_stair_id)
    #     if isinstance(ref_room_id, int):
    #         ref_room_id = ElementId(ref_room_id)

    #     room = self.doc.GetElement(ref_room_id)
    #     if not room:
    #         print("[ERROR] Room not found.")
    #         return
    #     stair = self.doc.GetElement(ref_stair_id)
    #     if not stair:
    #         print("[ERROR] Stair not found.")
    #         return

    #     # -------------------------------------
    #     # Step 2: Find the floor above the stair's room and Extract Bounding Box from Stair 
    #     level_above = self._find_level_above_room(room)
    #     level_above = self.doc.GetElement(ElementId(int(level_above)))
    #     floor_above = self._find_floor_closest_to_level(level_above)

    #     bbx_stair = stair.get_BoundingBox(None)

    #     # # ------------------------------------- 
    #     # STtep 3 # TODO: 
    #     # # Check if openings already exist (not yet implemented, this function can be unskippable)
    #     # # The reason is that if the cutting lines intersect, it's not acceptable by Revit.
    #     # line_ids = floor.GetDependentElements(ElementCategoryFilter(BuiltInCategory.OST_SketchLines))
    #     # for line_id in line_ids:
    #     #     line = self.doc.GetElement(line_id)
    #     #     if stair.get_Parameter(BuiltInParameter.STAIRS_TOP_LEVEL_PARAM).AsElementId() == floor.LevelId:
    #     #         if bbStairFilter.PassesFilter(line):
    #     #             topOpening.append(line.Id)
    #     #             mLinesTop.append(line)
    #     # if topOpening:
    #     #     print("[INFO] Opening already exists for this stair in the slab.")
    #     #     return

    #     # -------------------------------------
    #     # Step 4 Open SketchEditScope to draw opening curves
    #     # -------------------------------------
    #     sketch = self.doc.GetElement(floor_above.SketchId)
    #     sketchElevation = level_above.ProjectElevation

    #     sketchEditScope = SketchEditScope(self.doc, "Add Opening Above the Target Stair")
    #     sketchEditScope.Start(sketch.Id)

    #     t = Transaction(self.doc, "Sketch Opening")
    #     t.Start()

    #     try:
    #         minX, minY = bbx_stair.Min.X, bbx_stair.Min.Y
    #         maxX, maxY = bbx_stair.Max.X, bbx_stair.Max.Y
    #         z = sketchElevation

    #         curveArr = [
    #             Line.CreateBound(XYZ(minX, minY, z), XYZ(maxX, minY, z)),
    #             Line.CreateBound(XYZ(maxX, minY, z), XYZ(maxX, maxY, z)),
    #             Line.CreateBound(XYZ(maxX, maxY, z), XYZ(minX, maxY, z)),
    #             Line.CreateBound(XYZ(minX, maxY, z), XYZ(minX, minY, z)),
    #         ]

    #         for curve in curveArr:
    #             self.doc.Create.NewModelCurve(curve, sketch.SketchPlane)

    #         t.Commit()
    #         sketchEditScope.Commit(NoWarningsFailurePreprocessor())
    #         print("[INFO] Slab opening created successfully above stair.")

        # except Exception as e:
        
        #     print("[ERROR] Failed to sketch slab opening: {}".format(e))
        #     for line in traceback.format_exc().splitlines():
        #         print(line)
        #     t.RollBack()
        #     sketchEditScope.Cancel()