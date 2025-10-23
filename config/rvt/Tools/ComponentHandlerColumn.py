#! python3
# # IMPORT - BASIC PACKAGES 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#
import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
from System.Collections.Generic import *
from Autodesk.Revit.DB import FilteredElementCollector, ElementTransformUtils
from Autodesk.Revit.DB import ElementId, XYZ, Transaction, BuiltInCategory
from Autodesk.Revit.DB import Level, Structure, FamilySymbol, BuiltInParameter

# =====================================================================================================
# IMPORT - REVIT Batch UTILITIES
import revit_script_util
from revit_script_util import Output

# =====================================================================================================
# IMPORT - CUSTOM FUNCTIONS. 
from Tools.ComponentHandlerBase import NoWarningsFailurePreprocessor, ComponentHandlerBase

# =====================================================================================================
# CLASS - ComponentHandlerColumn (Subclass)

class ComponentHandlerColumn(ComponentHandlerBase):
    """
    Handler class for column-related functions.
    main functions:
    column_creation_by_shifting:            Create a new column by offsetting from a reference.
    column_movement_by_shifting:            Move a column by shifting in horizontal direction.
    """

    def __init__(self, doc):

        self.doc = doc
        self._get_sorted_levels(doc)

    def _get_column_location(self, column):
        location_point = column.Location
        if hasattr(location_point, 'Point'):
            return location_point.Point
        return None

    # ================================================
    # ================================================
    # ================================================
    # ================  C R E A T E  =================
    # ================================================
    # ================================================
    # ================================================
    def column_create(self, ref_column_id, params_column_create=[100.0, 0.0, 0.0]):
        """
        COLUMN - CREATE
        """

        offset_vector = XYZ(*params_column_create)
        creation_parameters = self._get_column_creation_parameters(ref_column_id, offset_vector)
        
        if not creation_parameters:
            return None
        new_location, column_type, level, height = creation_parameters

        return self._create_column_at_location(new_location, column_type, level, height)

    def _get_column_creation_parameters(self, ref_column_id, offset_vector):
        """
        COLUMN - CREATE: Part 1.
        """
        if isinstance(ref_column_id, int):
            ref_column_id = ElementId(ref_column_id)

        ref_column = self.doc.GetElement(ref_column_id)
        location = self._get_column_location(ref_column)
        if not location:
            print("[ERROR] Reference column has no valid location.")
            return None

        new_location = location.Add(offset_vector)
        # print("reference location", location)
        # print("offset_vector", offset_vector)
        # print("new location", new_location)

        column_type = self.doc.GetElement(ref_column.GetTypeId())
        level = self.doc.GetElement(ref_column.LevelId)

        top_level_id = ref_column.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).AsElementId()
        top_level = self.doc.GetElement(top_level_id)

        bottom_elev = level.Elevation if level else 0.0
        top_elev = top_level.Elevation if top_level else bottom_elev + 3.0 * 3.048
        height = top_elev - bottom_elev

        return new_location, column_type, level, height

    def _create_column_at_location(self, location, column_type=None, level=None, height=3.0 * 3.048):
        """
        COLUMN - CREATE: Part 2.
        """
        if not column_type:
            column_type = FilteredElementCollector(self.doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_StructuralColumns).FirstElement()
        
        if not level:
            level = FilteredElementCollector(self.doc).OfClass(Level).FirstElement()

        if not column_type.IsActive:
            column_type.Activate()
            self.doc.Regenerate()

        t = Transaction(self.doc, "Create Column")
        try:
            t.Start()
            new_column = self.doc.Create.NewFamilyInstance(
                location,
                column_type,
                level,
                Structure.StructuralType.Column
            )

            # Optional: Set height parameter
            top_offset = new_column.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM)
            if top_offset:
                top_offset.Set(height)

            t.Commit()
            print("[INFO] Column created successfully.")
            return new_column
        except Exception as e:
            print("[ERROR] Failed to create column: {}".format(e))
            t.RollBack()
            return None
        
    # ================================================
    # ================================================
    # ================================================
    # ================  M O D I F Y  =================
    # ================================================
    # ================================================
    # ================================================
    def column_modify(self, ref_column_id, params_column_modify=[100.0, 0.0, 0.0]):
        """
        COLUMN - MODIFY
        """
        offset_vector = XYZ(*params_column_modify)

        return self._column_movement_by_shifting(ref_column_id, offset_vector)
    
    def _column_movement_by_shifting(self, ref_column_id, offset_vector):
        """
        COLUMN - MODIFY: Part 1./All.
        """
        if isinstance(ref_column_id, int):
            ref_column_id = ElementId(ref_column_id)

        ref_column = self.doc.GetElement(ref_column_id)
        if not ref_column:
            print("[ERROR] Invalid column ID.")
            return None

        try:
            t = Transaction(self.doc, "Shift Column")
            t.Start()
            ElementTransformUtils.MoveElement(self.doc, ref_column.Id, offset_vector)
            t.Commit()
            print("[INFO] Column moved successfully.")
            return ref_column
        except Exception as e:
            print("[ERROR] Failed to move column: {}".format(e))
            if t.HasStarted():
                t.RollBack()
            return None
        
    # ================================================
    # ================================================
    # ================================================
    # ================  D E L E T E  =================
    # ================================================
    # ================================================
    # ================================================

    def column_delete(self, ref_column_id):
        """
        COLUMN - DELETE.
        """
        if isinstance(ref_column_id, int):
            ref_column_id = ElementId(ref_column_id)

        ref_column = self.doc.GetElement(ref_column_id)
        if not ref_column:
            print("[ERROR] Column not found.")
            return None

        try:
            t = Transaction(self.doc, "Delete Column")
            t.Start()
            self.doc.Delete(ref_column.Id)
            t.Commit()
            print("[INFO] Column deleted successfully.")
            return True
        except Exception as e:
            print("[ERROR] Failed to delete column: {}".format(e))
            if t.HasStarted():
                t.RollBack()
            return False
    
    # ================================================
    # ================================================
    # ================================================
    # ================  S  W  A  P  =================
    # ================================================
    # ================================================
    # ================================================
    # # TODO: to test later.
    # def column_swap(self, ref_column_id, new_type_id):
    #     """
    #     COLUMN - SWAP.
    #     """
    #     if isinstance(ref_column_id, int):
    #         ref_column_id = ElementId(ref_column_id)

    #     ref_column = self.doc.GetElement(ref_column_id)
    #     if not ref_column:
    #         print("[ERROR] Column not found.")
    #         return None

    #     try:
    #         t = Transaction(self.doc, "Replace Column Type")
    #         t.Start()
    #         ref_column.Symbol = self.doc.GetElement(ElementId(new_type_id))
    #         t.Commit()
    #         print("[INFO] Column type replaced successfully.")
    #         return ref_column
    #     except Exception as e:
    #         print("[ERROR] Failed to replace column type: {}".format(e))
    #         if t.HasStarted():
    #             t.RollBack()
    #         return None