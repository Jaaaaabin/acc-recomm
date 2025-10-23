# IMPORT - BASIC PACKAGES 
# ==================================================
#
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
import Autodesk
from System.Collections.Generic import *
from Autodesk.Revit.DB import SpatialElementBoundaryOptions
from Autodesk.Revit.DB import XYZ, FilteredElementCollector, BuiltInCategory, BuiltInParameter

# IMPORT - CUSTOM FUNCTIONS. 
# ==================================================
#

# SET - DOC 
# ==================================================
#
doc     = __revit__.ActiveUIDocument.Document

# FUNCTIONS 
# ==================================================
#

# ==================================================
# CLASS - BuildingElement (Base Class)
# ==================================================

class ElementTargetSelector:
    """
    Selects Revit elements based on IFC type names using a hardcoded mapping.
    Can process all model elements or filter from a pre-selected list.
    """

    # IFC-to-Revit Category Mapping (Hardcoded)
    IFC_TO_REVIT_MAPPING = {
        "IfcWall": BuiltInCategory.OST_Walls,
        "IfcSlab": BuiltInCategory.OST_Floors,
        "IfcColumn": BuiltInCategory.OST_Columns,
        "IfcWindow": BuiltInCategory.OST_Windows,
        "IfcDoor": BuiltInCategory.OST_Doors,
        "IfcRoof": BuiltInCategory.OST_Roofs,
        "IfcSpace": BuiltInCategory.OST_Rooms,
        "IfcStair": BuiltInCategory.OST_Stairs,
        "IfcRamp": BuiltInCategory.OST_Ramps,
        "IfcBuildingElementProxy": BuiltInCategory.OST_GenericModel,
        "IfcWallStandardCase": BuiltInCategory.OST_Walls,
        "IfcBeam": BuiltInCategory.OST_StructuralFraming,
    }

    def __init__(self, selected_elements=None):
        """
        Initializes the ElementTargetSelector.
        :param selected_elements: Optional list of pre-selected elements to filter.
        """
        self.current_selection = selected_elements if selected_elements else self._get_elements()

    def _get_elements(self):
        """Returns all model elements if no selection is provided."""
        return list(FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements())

    def select_by_ifc_types(self, ifc_types):
        """
        Select elements by IFC type names and store them in `self.current_selection`.
        :param ifc_types: List of IFC type names (e.g., ["IfcWall", "IfcSpace"])
        """
        matching_elements = []

        for ifc_type in ifc_types:
            if ifc_type in ElementTargetSelector.IFC_TO_REVIT_MAPPING:
                revit_category = ElementTargetSelector.IFC_TO_REVIT_MAPPING[ifc_type]

                # Ensure valid category mapping
                if isinstance(revit_category, BuiltInCategory):
                    filtered_elements = [
                        el for el in self.current_selection
                        if el.Category and el.Category.Id.IntegerValue == int(revit_category)
                    ]
                    matching_elements.extend(filtered_elements)

                else:
                    print("Warning: Invalid category mapping for IFC type:", ifc_type)

            else:
                print("Warning: IFC type not mapped -", ifc_type)

        self.current_selection = matching_elements  # Store filtered results
        print("Total matching elements found:", len(matching_elements))

    def select_by_ifc_guids(self, ifc_guids):
        """
        Select elements by IFC GUID and store them in `self.current_selection`.
        :param ifc_guids: List of IFC GUIDs (as strings)
        """
        matching_elements = []
        ifc_guids = set(g.strip() for g in ifc_guids)  # Ensure fast lookup

        for element in self.current_selection:
            param = element.get_Parameter(BuiltInParameter.IFC_GUID)

            if param and param.HasValue and param.AsString():
                element_ifc_guid = param.AsString().strip()
                if element_ifc_guid in ifc_guids:
                    matching_elements.append(element)

        self.current_selection = matching_elements  # Store results
        print("Found", len(matching_elements), "elements matching IFC GUIDs")

    def select_by_overlap(self, other_elements):
        """
        Update `self.current_selection` by keeping only elements that exist in `other_elements`.
        :param other_elements: List of elements to compare with current selection.
        """
        if not isinstance(other_elements, list):
            print("Error: `other_elements` must be a list of Revit elements.")
            return

        # Convert other_elements to a set of ElementIds for faster lookup
        other_element_ids = {el.Id for el in other_elements}

        # Filter current_selection to retain only overlapping elements
        self.current_selection = [el for el in self.current_selection if el.Id in other_element_ids]

        print("Updated selection with overlap:", len(self.current_selection), "elements")