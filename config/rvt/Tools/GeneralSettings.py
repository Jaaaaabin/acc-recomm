#! python3
# # IMPORT - BASIC PACKAGES 
# ==================================================
#
import clr
import json
clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
import Autodesk
from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory, XYZ, UnitUtils, UnitTypeId, Level, Curve
from Autodesk.Revit.DB import ViewFamilyType, ViewFamily, ViewPlan
from System.Collections.Generic import *
from System.Collections.Generic import List

# IMPORT - CUSTOM FUNCTIONS. 
# ==================================================
#

# SET - DOC 
# ==================================================
#
# doc     = __revit__.ActiveUIDocument.Document

# FUNCTIONS 
# ==================================================
#
def read_json_data(file_path):

    with open(file_path, 'r') as file:
        data = json.load(file)
    return data
    
def write_json_data(file_path, data):
    
    filtered_data = {k: v for k, v in data.items() if v}
    
    if filtered_data:
        with open(file_path, 'w') as json_file:
            json.dump(filtered_data, json_file, indent=4)

def find_active_phase(doc):
    phases = list(FilteredElementCollector(doc).OfClass(Autodesk.Revit.DB.Phase))
    if phases:
        return phases[-1]  # Return the last phase as the most recent
    return None

def extract_instance_attributes(original_instance, name_key="id"):
    """
    Extracts a simplified attribute dictionary from an object instance.
    Returns:
        - key: the instance's identity.id
        - value: filtered attributes dictionary (excluding complex nested objects and the id itself)
    """
    all_attributes = dict(original_instance.__dict__)
    
    identity = all_attributes.get("identity", None)
    instance_id = getattr(identity, name_key, "unknown")
    
    filtered_attributes = {
        k: v for k, v in all_attributes.items()
        if not hasattr(v, "__dict__") and k != name_key
    }

    return instance_id, filtered_attributes

def convert_internal_units(value, get_internal=True):
    # type: (float, bool) -> float
    
    """Function to convert Internal units to meters or vice versa.
    :param value:        Value to convert
    :param get_internal: True - Convert TO Internal / Flase - Convert FROM Internal
    :return:             Length in Internal units or Meters."""
    
    if get_internal:
        return UnitUtils.ConvertToInternalUnits(value, UnitTypeId.Meters)
    return UnitUtils.ConvertFromInternalUnits(value, UnitTypeId.Meters)

def location_to_XYZPoints(element_loc):

    pt1 = XYZ(
        convert_internal_units(element_loc[0][0],get_internal=True),
        convert_internal_units(element_loc[0][1],get_internal=True),
        convert_internal_units(element_loc[0][2],get_internal=True))
    pt2 = XYZ(
        convert_internal_units(element_loc[1][0],get_internal=True),
        convert_internal_units(element_loc[1][1],get_internal=True),
        convert_internal_units(element_loc[1][2],get_internal=True))
    
    return pt1, pt2


def create_levels(doc, level_elevations, level_names):
    
    level_ids = []
    for elevation, name in zip(level_elevations, level_names):
        elevation_feet = convert_internal_units(elevation, get_internal=True)
        level = Level.Create(doc, elevation_feet)
        level.Name = name
        level_ids.append(level.Id)
    
    return level_ids

def delete_levels(doc, exclude_ids):

    all_levels = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Levels).WhereElementIsNotElementType().ToElements()
    for level in all_levels:
        if level.Id not in exclude_ids:
            doc.Delete(level.Id)

def create_plan_views_for_all_levels(doc):

    def create_plan_view_for_level(doc, level):
        
        view_family_type = None
        view_family_types = FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements()
        for vft in view_family_types:
            if vft.ViewFamily == ViewFamily.FloorPlan:
                view_family_type = vft
                break
        
        if not view_family_type:
            print("No ViewFamilyType found for Floor Plan.")
            return None
        
        # Create a new Plan View for the level
        plan_view = ViewPlan.Create(doc, view_family_type.Id, level.Id)
        plan_view.Name ="FloorPlan-" + str(level.Name)
        return plan_view
    
    # Collect all levels
    all_levels = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Levels).WhereElementIsNotElementType().ToElements()
    
    # Create a plan view for each level
    for level in all_levels:
        create_plan_view_for_level(doc, level)

def location_dict_to_XYZPoints(location_dict):
    
    pt = None

    if "x" in location_dict and "y" in location_dict and "z" in location_dict:
        pt = XYZ(
        convert_internal_units(location_dict["x"],get_internal=True),
        convert_internal_units(location_dict["y"],get_internal=True),
        convert_internal_units(location_dict["z"],get_internal=True))

    return pt

def convert_python_to_curve_list(py_list):
    curve_list = List[Curve]()
    for item in py_list:
        curve_list.Add(item)  # Lines are subclasses of Curve
    return curve_list