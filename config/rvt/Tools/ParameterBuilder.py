# -*- coding: utf-8 -*-

# - - - - - - - - - - - - - 
## import revit api bases
import os
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')

from Autodesk.Revit.DB import ElementId
from Autodesk.Revit.DB import GlobalParametersManager, GlobalParameter, ParameterType, DoubleParameterValue
from System.Collections.Generic import *

from GeometryHelper import location_to_XYZPoints, convert_internal_units

def set_one_GlobalParameter_byDimension(doc, gp_name, ref_dim=[], gp_type=ParameterType.Length):

    # The element id of the global parameter is provided by the FindByName method.
    existing_param_id = GlobalParametersManager.FindByName(doc, gp_name)
    if existing_param_id.ToString() != "-1":
        doc.Delete(existing_param_id) # If there's already a global parameter with the same name

    if ref_dim:

        gp_value = DoubleParameterValue(ref_dim.Value)
        param = GlobalParameter.Create(doc, gp_name, gp_type) # Create a new global parameter 
        param.SetValue(gp_value)
        return param
    
    else:
        return None

def label_dimension_by_GlobalParameter(dim, gp):

    if gp.CanLabelDimension(dim.Id):
        gp.LabelDimension(dim.Id)

def generate_and_set_formular_with_delta(doc, target_gp_id, ref_gp_id, delta_gp_id, measure_tolerance = 1e-3):

    # Retrieve the global parameters
    target_gp = doc.GetElement(ElementId(target_gp_id))
    ref_gp = doc.GetElement(ElementId(ref_gp_id))
    delta_gp = doc.GetElement(ElementId(delta_gp_id))

    if not target_gp or not ref_gp or not delta_gp:
        raise ValueError("One or more global parameters not found")

    # Get the values of the global parameters
    target_value = target_gp.GetValue().Value
    ref_value = ref_gp.GetValue().Value
    delta_value = delta_gp.GetValue().Value
    
    # Determine the formula based on the values
    if abs(target_value + delta_value - ref_value) < measure_tolerance:
        formula = "{} - {}".format(ref_gp.Name, delta_gp.Name)
    elif abs(target_value - delta_value - ref_value) < measure_tolerance:
        formula = "{} + {}".format(ref_gp.Name, delta_gp.Name)
    else:
        raise ValueError("The values of the parameters do not meet the conditions for a valid equal formula")
    
    # # Set the formula for the target global parameter
    target_gp.SetFormula(formula)
    
    return formula

        