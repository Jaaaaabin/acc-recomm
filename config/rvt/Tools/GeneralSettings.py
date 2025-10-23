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


# # =============================================================================
# # copied from previous projects.
# # =============================================================================
# # to incorporate in the near futuer after building up the theoretical part.
# def releaseConstraintByGP(
#     doc,
#     key_gp,
#     del_dm=False,
#     del_gp=False,
#     ):

#     """
#     release the Constraints (linkages between Global Parameters and Dimensions)
#     and flexiblely delete the GlobalParameters and Dimensions.
#     """

#     # find all existing constraints in the model.
#     allconstraintElements = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Constraints).ToElements()
#     allconstraintIds = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Constraints).ToElementIds()

#     # create blank List for ids (dimensions and global parameters.)
#     allUnlabeledGPElements = []
#     ids_DimensionToDelete = List[ElementId]()
#     ids_ParameterToDelete = List[ElementId]()

#     for cstElement, cstId in zip(allconstraintElements, allconstraintIds):
#         cstLabel = cstElement.GetParameters('Label')

#         # if there's a Global Parameter labelling this dimension/constraint.
#         if cstLabel:

#             cstLabelGPId = cstLabel[0]
#             cstLabelGPId = cstLabelGPId.AsElementId()
#             cstLabelGPElement = doc.GetElement(cstLabelGPId)

#             if key_gp in cstLabelGPElement.Name:
#                 # archive DimensionIds
#                 ids_DimensionToDelete.Add(cstId)
#                 ids_ParameterToDelete.Add(cstLabelGPId)
                
#                 allUnlabeledGPElements.append(cstLabelGPElement.Name)
#                 cstLabelGPElement.UnlabelDimension(cstId)
    
#     # delete all related Dimensions by Ids.(should add option to delete all Dimensions.)
#     if del_dm:
#         for id in ids_DimensionToDelete:
#             if DocumentValidation.CanDeleteElement(doc,id):
#                 doc.Delete(id)

#     # delete all related Global Parameters by Ids.(should add option to delete all GlobalParameters)
#     if del_gp:
#         for id in ids_ParameterToDelete:
#             if DocumentValidation.CanDeleteElement(doc,id):
#                 doc.Delete(id)

#     return 'Succeed.'

# def pin_unpin_elements(element_selection, triggle='pin'):

#     if triggle =='pin':
#         for elem in element_selection:
#             Element.Pinned.SetValue(elem, True)
#     elif triggle =='unpin':
#         for elem in element_selection:
#             Element.Pinned.SetValue(elem, False)

# def fresh_GlobalParameter(
#         doc, names, values, set_foot_to_meter=False):
#     """
#     Fresh global parameters / fresh a list of global parameters
#     till now, only for doubleparametervalues...
#     """

#     # # Fix the unit problem
#     # def foot_to_meter(ori_value):
#     #     if isinstance(ori_value, list):
#     #         return [UnitUtils.ConvertToInternalUnits(value, UnitTypeId.Meters) for value in ori_value]
#     #     return float(UnitUtils.ConvertToInternalUnits(ori_value, UnitTypeId.Meters))
    
#     if set_foot_to_meter:
#         values = foot_to_meter(values)
    
#     # Update the parameter values

#     for ii in range(len(names)):
#         name = names[ii]
#         value = values[ii]
#         gp_id = Autodesk.Revit.DB.GlobalParametersManager.FindByName(doc, name)
#         gp_element = doc.GetElement(gp_id)
#         gp_value = gp_element.GetValue().Value
        
#         # set tolerance for not changing the value of the Global Parameter.
#         if abs(value - gp_value) < 0.00001:
#             continue
#         else:
#             gp_element.SetValue(DoubleParameterValue(value))

#     def varyGPs(ext_doc, savepath, gp_names, gp_values):
#         """
#         vary the IfcGUIDs among multiple external Docuents.
#         """

#         # release from lists.
#         if isinstance(ext_doc, list):
#             ext_doc = ext_doc[0]
#         if isinstance(savepath, list):
#             savepath = savepath[0]

#         # start the Transaction Processes in the external Document.
#         with Transaction(ext_doc, "varyGPs") as t:
#             t.Start()

#             # handle and preprocess the warnings.
#             # options = t.GetFailureHandlingOptions()
#             # options.SetFailuresPreprocessor(WallWarningSwallower(IFailuresPreprocessor))
#             # t.SetFailureHandlingOptions(options)

#             # - - - - - - 
#             # varyDesign
#             fresh_GlobalParameter(
#                 ext_doc, gp_names, gp_values, set_foot_to_meter=True) # important:set_foot_to_meter=True.
#             # - - - - - - 

#             # end the Transaction Processes in the external Document.
#             t.Commit()
#             # t.Dispose()

#         # save the processed Document.
#         optionSave = SaveAsOptions()
#         optionSave.OverwriteExistingFile = True
#         ext_doc.SaveAs(savepath, optionSave)

#         tempo = 'succeed'

#         return tempo

# def load_families_from_directory(doc, family_directory=[]):

#     if family_directory:
        
#         family_paths = []
#         for root, dirs, files in os.walk(family_directory):
#             for file in files:
#                 if file.endswith(".rfa"):
#                     full_path = os.path.join(root, file)
#                     family_paths.append(full_path)
        
#         for p in family_paths:
#             doc.LoadFamily(p)
    
# def get_elements_by_ifcguids(doc, identity_IfcGuids=None, element_category=None):
    
#     if identity_IfcGuids is None:
#         return 'Please enter a IfcGUID or a list of IfcGUIDs.'

#     if element_category is None:
#         element_category = [
#             BuiltInCategory.OST_Walls,
#             BuiltInCategory.OST_StructuralColumns
#         ]
#         # Note: There's issues with BuiltInCategory.OST_Windows, BuiltInCategory.OST_Doors

#     multiFilter = ElementMulticategoryFilter(List[BuiltInCategory](element_category))
#     scope_elements = FilteredElementCollector(doc).WherePasses(multiFilter).WhereElementIsNotElementType().ToElements()
    
#     # Create a dictionary to map IfcGUIDs to elements
#     scope_element_dict = {elem.GetParameters("IfcGUID")[0].AsString(): elem for elem in scope_elements}

#     if isinstance(identity_IfcGuids, list):
#         # Return elements matching the list of IfcGUIDs
#         target_elements = [scope_element_dict[guid] for guid in identity_IfcGuids if guid in scope_element_dict]
#     else:
#         # Return the element matching the single IfcGUID
#         target_elements = [scope_element_dict.get(identity_IfcGuids)] if identity_IfcGuids in scope_element_dict else []

#     return target_elements

# def create_one_column(doc, location_point, family_symbol, level_id):

#     # NewFamilyInstance Method (XYZ, FamilySymbol, Level, StructuralType)
#     st_column = doc.Create.NewFamilyInstance(location_point, family_symbol, level_id, StructuralType.Column)
#     return st_column

# def create_one_wall(doc, curve, wall_type_id, level_id, height):

#     # Create Method (Document, Curve, ElementId, ElementId, Double, Double, Boolean, Boolean)
#     ns_wall = Wall.Create(doc, curve, wall_type_id, level_id, height, 0, True, True)
#     return ns_wall

# # Function to create a door on a wall at a specified location
# def create_one_door(doc, wall, door_location_pt, door_symbol):
    
#     if not door_symbol.IsActive:
#         door_symbol.Activate()
#         doc.Regenerate()
    
#     door_instance = doc.Create.NewFamilyInstance(door_location_pt, door_symbol, wall, StructuralType.NonStructural)

#     return door_instance

# # Function to create a window on a wall at a specified location
# def create_one_window(doc, wall, window_location_pt, window_symbol):
    
#     if not window_symbol.IsActive:
#         window_symbol.Activate()
#         doc.Regenerate()
    
#     window_instance = doc.Create.NewFamilyInstance(window_location_pt, window_symbol, wall, StructuralType.NonStructural)

#     return window_instance

# def create_column_type(doc, base_name_key, new_dimensions, new_key):

#     # Find the base column type to duplicate
#     collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralColumns).WhereElementIsElementType().ToElements()
#     base_column_type = None
#     new_name = "-".join(
#         (new_key, str(new_dimensions["Length"]), str(new_dimensions["Width"]), str(new_dimensions["Thickness"])))

#     # Match the basis
#     for column_type in collector:
#         column_type_name = column_type.Name.AsString() if hasattr(column_type, 'Name') else column_type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
#         if base_name_key in column_type_name:
#             base_column_type = column_type
#             break
    
#     # Duplicate the base column type
#     new_column_type = base_column_type.Duplicate(new_name)

#     # Reset the column dimensions 
#     for k, v in new_dimensions.items():
#         column_param = new_column_type.LookupParameter(k)
#         if column_param:
#             column_param.Set(v)

#     return new_column_type

# # Compound Layer Structure: https://thebuildingcoder.typepad.com/blog/2012/03/updating-wall-compound-layer-structure.html

# def create_wall_type(doc, base_name_key, new_parameter, st_ns_ct='', set_multi_layers=False):
    
#     # Get the Name for the new wall type.
#     if set_multi_layers:
#         new_name = 'MurPlus-' + base_name_key + '-' + st_ns_ct + '-' + str(new_parameter) # new_parameter: scaler for all layer widths.
#     else:
#         # new_parameter is real value.
#         new_name = 'Mur-' + base_name_key + '-' + st_ns_ct + '-' + str(new_parameter) # new_parameter: real width value for the first core layer.
#         new_parameter = convert_internal_units(new_parameter, get_internal=True)

#     # Get the wall type as basis. 
#     base_wall_type = None
#     collector = FilteredElementCollector(doc).OfClass(WallType).WhereElementIsElementType().ToElements()
    
#     # Match the basis wall type.
#     for wall_type in collector:
#         wall_type_name = wall_type.Name.AsString() if hasattr(wall_type, 'Name') else wall_type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
#         if base_name_key in wall_type_name:
#             base_wall_type = wall_type
#             break
    
#     # Duplicate the base wall type
#     new_wall_type = base_wall_type.Duplicate(new_name)
    
#     if st_ns_ct == 'ct':
        
#         return new_wall_type
    
#     else:
#         # Query the CompoundStructure and its layers.
#         compound_structure = new_wall_type.GetCompoundStructure()
#         layers = compound_structure.GetLayers()
        
#         if set_multi_layers:

#             # Change all layers proportionally.
#             for index, lay in enumerate(layers):
#                 mat_id   = lay.MaterialId
#                 width_feet = lay.Width
#                 compound_structure.SetLayerWidth(index, width_feet*new_parameter)

#                 # width_meter = width_feet * 0.3048
#                 # if mat_id == ElementId(-1):  #lementId(-1) Means None
#                 #     mat_name = None
#                 # else:
#                 #     mat      = doc.GetElement(mat_id)
#                 #     mat_name = mat.Name
#         else:
#             # Change only the First Core Layer with FirstCoreLayerIndex
#             core_layer_index = compound_structure.GetFirstCoreLayerIndex()
#             compound_structure.SetLayerWidth(core_layer_index, new_parameter)
        
#         new_wall_type.SetCompoundStructure(compound_structure)
        
#         return new_wall_type

# def select_column_type(collector_of_column_types, key_type_name, selection_parameter=[], threshold_parameter=1e-3):
    
#     # choose from the existing column_FamilySymbols in the project.
#     seen = None
#     for column_FamilySymbol in collector_of_column_types:
        
#         column_type_name = column_FamilySymbol.Name.AsString() if hasattr(column_FamilySymbol, 'Name') else column_FamilySymbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
#         if key_type_name in column_type_name:
            
#             if selection_parameter:
#                 column_selection_parameter = column_FamilySymbol.LookupParameter("Width").AsDouble()
#                 # column_selection_parameter = convert_internal_units(column_selection_parameter, get_internal=False) # No need for unit change.     
            
#                 if abs(selection_parameter-column_selection_parameter) < threshold_parameter:
#                     print ("The selected column_type_name is ", column_type_name)
#                     seen = column_FamilySymbol    
#                     break
            
#             else:
#                 print ("The selected column_type_name is ", column_type_name)
#                 seen = column_FamilySymbol
    
#     if seen is None:
#         raise ValueError("No suitable column type found in 'select_column_type'")
#     else:
#         return seen

# def select_wall_type(collector_of_wall_types, key_type_name, selection_parameter=[], threshold_parameter=1e-3):
    
#     # choose from the existing wall_ElementType in the project.
#     seen = None
#     for wall_type in collector_of_wall_types:
        
#         wall_type_name = wall_type.Name.AsString() if hasattr(wall_type, 'Name') else wall_type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()  
#         if key_type_name in wall_type_name:
            
#             if selection_parameter:
#                 wall_selection_parameter = wall_type.LookupParameter("Width").AsDouble()
#                 wall_selection_parameter = convert_internal_units(wall_selection_parameter, get_internal=False) # has need for unit change.
                
#                 if abs(selection_parameter-wall_selection_parameter) < threshold_parameter:
#                     print ("The selected wall_type_name is ", wall_type_name)
#                     seen = wall_type    
#                     break
#             else:
#                 print ("The selected wall_type_name is ", wall_type_name)
#                 seen = wall_type
    
#     if seen is None:
#         raise ValueError("No suitable wall type found in 'select_wall_type'")
#     else:
#         return seen

# def get_wall_location_curve(element_wall):
    
#     wall_location = element_wall.Location
    
#     if isinstance(wall_location, LocationCurve):
#         wall_curve =  wall_location.Curve
#         return wall_curve
    
#     elif isinstance(wall_location, LocationPoint):
#         # feasible.
#         wall_point = wall_location.Point
#         start_point = XYZ(
#             convert_internal_units(wall_point.X - 5, get_internal=True), 
#             convert_internal_units(wall_point.Y, get_internal=True), 
#             convert_internal_units(wall_point.Z, get_internal=True))
#         end_point = XYZ(
#             convert_internal_units(wall_point.X + 5, get_internal=True), 
#             convert_internal_units(wall_point.Y, get_internal=True), 
#             convert_internal_units(wall_point.Z, get_internal=True))
#         wall_curve = Line.CreateBound(start_point, end_point)
        
#         return wall_curve
    
#     else:
#         raise ValueError("Uncovered cases for the location of the wall.")
