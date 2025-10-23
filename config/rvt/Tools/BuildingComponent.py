#! python3
# # IMPORT - BASIC PACKAGES 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
import Autodesk
from System.Collections.Generic import *
from Autodesk.Revit.DB import SpatialElementBoundaryOptions
from Autodesk.Revit.DB import XYZ, FilteredElementCollector, BuiltInCategory, BuiltInParameter, ElementId
from Autodesk.Revit.DB import Wall, ModelCurve

# IMPORT - CUSTOM FUNCTIONS. 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# #
# from GeneralSettings import find_active_phase
# from GeometryHelper import calculate_bbx_overlap_volume_by_minmax_xyz

# SET - DOC 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#
# doc     = __revit__.ActiveUIDocument.Document

# FUNCTIONS 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#

FT_PER_M = 3.280839895013123
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - AttributeHandler (Base Class)
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class AttributeHandler:
    """
    Provides attribute printing functionality, handling nested objects and dictionaries.
    Ensures embedded objects print first, followed by normal attributes, then dictionaries.
    """

    def print_attributes(self, indent=0):
        """
        Prints all attributes of the class.
        - Embedded objects print first.
        - Normal attributes print second.
        - Dictionaries print last.
        """
        spacing = "    " * indent
        print("\n----------------------------------------------------------------")
        print(spacing + "Attributes of " + self.__class__.__name__ + ":")

        attributes = list(self.__dict__.items())

        # Categorize attributes
        embedded_objects = [(attr, value) for attr, value in attributes if hasattr(value, "__dict__")]
        normal_values = [(attr, value) for attr, value in attributes if not isinstance(value, dict) and not hasattr(value, "__dict__")]
        dict_values = [(attr, value) for attr, value in attributes if isinstance(value, dict)]

        # Print in specific order: first normal attributes, then dicts, the embedded_objects at the end
        for attr, value in normal_values:
            self._print_attributes(attr, value, indent + 1)

        for attr, value in dict_values:
            print(spacing + "  " + attr + " (dict):")
            for key, sub_value in value.items():
                self._print_attributes(key, sub_value, indent + 2)

        # no need to print the embedded objects in the newest version.
        for attr, value in embedded_objects:
            print(spacing + "  " + attr + " (object):")
            value.print_attributes(indent + 2)  # Recursively print object attributes

    def _print_attributes(self, key, value, indent):
        """
        Helper function to print values properly with indentation.
        """
        spacing = "    " * indent
        print(spacing + "- " + str(key) + ": " + str(value))

# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - IdentityHandler
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class IdentityHandler(AttributeHandler):
    """
    Handles fundamental identity attributes such as ID and IFC GUID for Revit elements.
    """
    def __init__(self, element):
        """
        Initialize fundamental properties: ID and IFC GUID.
        """
        self.id = str(element.Id)
        self.ifc_guid = str(self.get_parameter_value(element, BuiltInParameter.IFC_GUID))
        self.level_id = str(self.get_level(element))
        
    @staticmethod
    def get_parameter_value(element, param_enum):
        """
        Retrieve a parameter value from an element.
        """
        param = element.get_Parameter(param_enum)
        return param.AsString() if param and param.HasValue else ''
    
    @staticmethod
    def get_level(element):
        """
        Retrieves the level name of the element using LevelId.
        """
        level_id = element.LevelId if hasattr(element, 'LevelId') else None
        return level_id

# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - SlabComponent
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class SlabComponent(AttributeHandler):
    """
    Standalone class that reuses IdentityHandler logic without inheritance.
    Extracts slab center location.
    """
    def __init__(self, element, doc):

        self.identity = IdentityHandler(element)
        self.location = self.get_location(element)
        self.level_id = self.identity.level_id
        self.id = self.identity.id
        self.ifc_guid = self.identity.ifc_guid

        self.location = [v / FT_PER_M if v is not None else None for v in self.location]

    def get_location(self, element):
        """
        Extracts the center XYZ coordinates of the slab using its bounding box.
        """
        slab_bbx = element.get_BoundingBox(None)
        if slab_bbx:
            return [(slab_bbx.Min.X + slab_bbx.Max.X) / 2,
                    (slab_bbx.Min.Y + slab_bbx.Max.Y) / 2,
                    (slab_bbx.Min.Z + slab_bbx.Max.Z) / 2]
        return None
    
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - RoomComponent
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class RoomComponent(AttributeHandler):
    """
    Standalone class that reuses IdentityHandler logic without inheritance.
    """
    def __init__(self, element, doc):

        self.identity = IdentityHandler(element)
        self.location = self.get_location(element)
        self.level_id = self.identity.level_id
        self.id = self.identity.id
        self.ifc_guid = self.identity.ifc_guid
        
        bound_phy_raw, bound_vrt_raw = self.get_boundaries(element, doc)
        self.bound_phy, self.bound_vrt = self.get_boundaries(element, doc)
        self.bound_phy = list(set(bound_phy_raw or []))
        self.bound_vrt = list(set(bound_vrt_raw or []))
        
        # room identity fields
        self.name   = self.get_room_name(element)
        self.number = self.get_room_number(element)
        
        # room dimensions
        self.width, self.length = self.get_dimensions(element)
        
        self.width = self.width / FT_PER_M if self.width is not None else None
        self.length = self.length / FT_PER_M if self.length is not None else None
        self.location = [v / FT_PER_M if v is not None else None for v in self.location]
        
    def get_location(self, element):
        """
        Extracts the XYZ coordinates of the room's location.
        """
        if element.Location:
            return [element.Location.Point.X, element.Location.Point.Y, element.Location.Point.Z]
        return None
    
    def get_room_name(self, element):
        """
        Returns the room's display name (string) or None.
        Prefer parameter in case of localization or special cases.
        """
        p = element.get_Parameter(BuiltInParameter.ROOM_NAME)
        if p and p.AsString():
            return p.AsString()
        
        # Fallback: many Revit builds expose Room.Name
        return getattr(element, "Name", None)
    
    def get_room_number(self, element):
        """
        Returns the room number (string) or None.
        """
        p = element.get_Parameter(BuiltInParameter.ROOM_NUMBER)
        return p.AsString() if p and p.AsString() else None
    
    def get_boundaries(self, element, doc):
        """
        Extracts the room boundaries:
        - Physical boundaries (Walls)
        - Virtual boundaries (ModelCurves)
        """
        bound_phy = []
        bound_vrt = []

        boundary_options = SpatialElementBoundaryOptions()
        room_boundaries = element.GetBoundarySegments(boundary_options)

        for boundary_list in room_boundaries:
            for boundary_segment in boundary_list:
                boundary_element = doc.GetElement(boundary_segment.ElementId)
                if isinstance(boundary_element, Wall):
                    bound_phy.append(str(boundary_element.Id))
                elif isinstance(boundary_element, ModelCurve):
                    bound_vrt.append(str(boundary_element.Id))

        return bound_phy, bound_vrt
    
    def get_dimensions(self, element):
        """
        Approximate room dimensions (width and length) 
        using the bounding box of boundary segments.
        """
        boundary_options = SpatialElementBoundaryOptions()
        room_boundaries = element.GetBoundarySegments(boundary_options)

        points = []
        for boundary_list in room_boundaries:
            for boundary_segment in boundary_list:
                curve = boundary_segment.GetCurve()
                start, end = curve.GetEndPoint(0), curve.GetEndPoint(1)
                points.extend([start, end])

        if not points:
            return None, None

        min_x = min(p.X for p in points)
        max_x = max(p.X for p in points)
        min_y = min(p.Y for p in points)
        max_y = max(p.Y for p in points)

        width = min(max_x - min_x, max_y - min_y)
        length = max(max_x - min_x, max_y - min_y)

        return width, length

# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - WallComponent
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class WallComponent(AttributeHandler):
    """
    Standalone class that reuses IdentityHandler logic without inheritance.
    Extracts wall location (start & end points).
    """
    def __init__(self, element, doc): 
 
        self.identity = IdentityHandler(element)
        self.location = self.get_location(element)
        self.level_id = self.identity.level_id
        self.id = self.identity.id
        self.ifc_guid = self.identity.ifc_guid

        self.location = [v / FT_PER_M if v is not None else None for v in self.location]

        self.is_room_bounding = self.check_room_bounding(element)
        
    def check_room_bounding(self, element):
        """
        Returns True if the wall is room bounding, False if not, None if unavailable.
        """
        p = element.get_Parameter(BuiltInParameter.WALL_ATTR_ROOM_BOUNDING)
        if p:
            return bool(p.AsInteger())
        return None

    def get_location(self, element):
        """
        Extracts the start and end XYZ coordinates of the wall.
        """
        if isinstance(element.Location, Autodesk.Revit.DB.LocationCurve):
            try:
                start_point = element.Location.Curve.GetEndPoint(0)
                end_point = element.Location.Curve.GetEndPoint(1)
                return [start_point.X, start_point.Y, start_point.Z, 
                        end_point.X, end_point.Y, end_point.Z]
            except:
                return None
        return None

# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - DoorComponent
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class DoorComponent(AttributeHandler):
    """
    Standalone class that reuses IdentityHandler logic without inheritance.
    Extracts door location.
    """
    def __init__(self, element, doc):

        self.identity = IdentityHandler(element)
        self.location = self.get_location(element)
        self.level_id = self.identity.level_id
        self.id = self.identity.id
        self.ifc_guid = self.identity.ifc_guid

        self.location = [v / FT_PER_M if v is not None else None for v in self.location]

    def get_location(self, element):
        """
        Extracts the XYZ coordinates of the door's location.
        """
        # when door has the location (a location point.)
        if element.Location and hasattr(element.Location, 'Point') and element.Location.Point:
            return [element.Location.Point.X, element.Location.Point.Y, element.Location.Point.Z]
        
        # when door's location is null
        host_element = element.Host
        if isinstance(host_element.Location, Autodesk.Revit.DB.LocationCurve):
            try:
                start_point = host_element.Location.Curve.GetEndPoint(0)
                end_point = host_element.Location.Curve.GetEndPoint(1)
                return [
                    (start_point.X + end_point.X)*0.5,
                    (start_point.Y + end_point.Y)*0.5,
                    (start_point.Z + end_point.Z)*0.5]
            except:
                return None
        return None

# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - WindowComponent
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class WindowComponent(AttributeHandler):
    """
    Standalone class that reuses IdentityHandler logic without inheritance.
    Extracts window location.
    """
    def __init__(self, element, doc):

        self.identity = IdentityHandler(element)
        self.location = self.get_location(element)
        self.level_id = self.identity.level_id
        self.id = self.identity.id
        self.ifc_guid = self.identity.ifc_guid

        self.location = [v / FT_PER_M if v is not None else None for v in self.location]
        
    def get_location(self, element):
        """
        Extracts the XYZ coordinates of the window's location.
        """
        if element.Location:
            return [element.Location.Point.X, element.Location.Point.Y, element.Location.Point.Z]
        return None

# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - StructuralColumnComponent
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class StructuralColumnComponent(AttributeHandler):
    """
    Standalone class that reuses IdentityHandler logic without inheritance.
    Extracts column location (midpoint or bounding box).
    """
    def __init__(self, element, doc):

        self.identity = IdentityHandler(element)
        self.location = self.get_location(element, doc)
        self.level_id = self.identity.level_id
        self.id = self.identity.id
        self.ifc_guid = self.identity.ifc_guid

    def get_location(self, element, doc):
        """
        Extracts the column location:
        - Uses direct point if available.
        - Uses midpoint of curve for slanted columns.
        - Falls back to bounding box center if no valid location.
        """
        if element.Location:
            if hasattr(element.Location, 'Point'):
                z_level = doc.GetElement(element.LevelId).Elevation
                element_x = element.Location.Point.X
                element_y = element.Location.Point.Y
                element_z = element.Location.Point.Z + z_level
                return [element_x, element_y, element_z]
            elif hasattr(element.Location, 'Curve'):
                start_point = element.Location.Curve.GetEndPoint(0)
                end_point = element.Location.Curve.GetEndPoint(1)
                return [(start_point.X + end_point.X) / 2,
                        (start_point.Y + end_point.Y) / 2,
                        (start_point.Z + end_point.Z) / 2]
  
        # Fallback to bounding box center
        column_bbx = element.get_BoundingBox(None)
        if column_bbx:
            return [(column_bbx.Min.X + column_bbx.Max.X) / 2,
                    (column_bbx.Min.Y + column_bbx.Max.Y) / 2,
                    (column_bbx.Min.Z + column_bbx.Max.Z) / 2]
        
        return None

# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - StairComponent
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class StairComponent(AttributeHandler):
    """
    Standalone class that reuses IdentityHandler logic without inheritance.
    Extracts stair base & top elevations and overlapping elements (rooms/slabs).
    """
    def __init__(self, element, doc):

        self.identity = IdentityHandler(element)
        self.location = self.get_location(element)
        self.id = self.identity.id
        self.ifc_guid = self.identity.ifc_guid

        self.base_elevation = self.get_base_elevation(element)
        self.top_elevation = self.get_top_elevation(element)
    
        self.location = [v / FT_PER_M if v is not None else None for v in self.location]
        
        # todo. handle complex stair styles.
        self.horizontal_dimensions = [2.1, 3.0]

    def get_location(self, element):
        """
        Extracts the approximate location of the stair using its bounding box center.
        """
        stair_bbx = element.get_BoundingBox(None)
        if stair_bbx:
            return [
                (stair_bbx.Min.X + stair_bbx.Max.X) / 2,
                (stair_bbx.Min.Y + stair_bbx.Max.Y) / 2,
                (stair_bbx.Min.Z + stair_bbx.Max.Z) / 2
            ]
        return None
    
    def get_base_elevation(self, element):
        """
        Retrieves the base elevation of the stair.
        """
        return element.BaseElevation if hasattr(element, "BaseElevation") else None

    def get_top_elevation(self, element):
        """
        Retrieves the top elevation of the stair.
        """
        return element.TopElevation if hasattr(element, "TopElevation") else None

# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
# CLASS - SeparationLineComponent
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class SeparationLineComponent(AttributeHandler):
    """
    Standalone class to extract relevant attributes from Room Separation Lines (Model Lines with special role).
    Inherits from AttributeHandler.
    """
    def __init__(self, element, doc):
        self.identity = IdentityHandler(element)
        self.location = self.get_location(element)
        self.level_id = self.identity.level_id
        self.id = self.identity.id
        self.ifc_guid = self.identity.ifc_guid

        self.location = [v / FT_PER_M if v is not None else None for v in self.location]
        
    def get_location(self, element):
        """
        Extracts start and end XYZ coordinates for the line geometry.
        """
        if isinstance(element.Location, Autodesk.Revit.DB.LocationCurve):
            try:
                start = element.Location.Curve.GetEndPoint(0)
                end = element.Location.Curve.GetEndPoint(1)
                return [start.X, start.Y, start.Z, end.X, end.Y, end.Z]
            except:
                return None
        return None