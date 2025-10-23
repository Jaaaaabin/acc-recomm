"""
This is the basic module for healing visulization take place in Dyanmo for Autodesk Revit.
"""

# -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  - 
# Import general packages.


# -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  - 
# Import Revit/Dynamo API related packages
from Autodesk.Revit.DB import ElementId, BuiltInParameter, Color, OverrideGraphicSettings
from System.Collections.Generic import *
from RevitServices.Persistence import DocumentManager
import System

def setGraphicsStyle(views, style_number=2):
    """
    set the views in specified graphics style.
    1. Wireframe
    2. Hidden line
    3. Shaded
    4. Shaded with Edges
    5. Consistent Colors
    6.Realistic
    """
    
    if isinstance(views, list):
        for view in views:
            view.get_Parameter(BuiltInParameter.MODEL_GRAPHICS_STYLE).Set(style_number)
    else:
        views.get_Parameter(BuiltInParameter.MODEL_GRAPHICS_STYLE).Set(style_number)
    return "Succeed"  


def highlightSelection(items):
    """
    hight the elements by Selection.
    """
    
    uidoc = DocumentManager.Instance.CurrentUIApplication.ActiveUIDocument

    if isinstance(items, type(None)): # Select none
        items = []
    elif not hasattr(items, "__iter__"): # Check if single element
        items = [items]
        
    ids = List[ElementId](i.Id for i in items)
    uidoc.Selection.SetElementIds(ids)

    return "Succeed"


def convertColor(e):
    """
    convert the color to red green blue colors
    """
    return Color(e.Red, e.Green, e.Blue)


def overrideSpaceColor(e, c, v):
    """
    override the color pattern.
    e: space element
    c: color
    v: view

    """

    gSettings = OverrideGraphicSettings()
    gSettings.SetSurfaceForegroundPatternColor(c)
    v.SetElementOverrides(e.Id, gSettings)
    return e


def overrideSpaceDisplay(elements, element_color, level_views):
    errorReport = None
    
    c = convertColor(element_color)
    output = []
    for elem, view in zip(elements, level_views):
        output.append(overrideSpaceColor(elem, c, view))
    
    return errorReport


def overrideElementColor(e, c, v):
    """
    override the color pattern.
    e: building element
    c: color
    v: view

    """

    gSettings = OverrideGraphicSettings()
    gSettings.SetCutLineColor(c)
    gSettings.SetCutForegroundPatternColor(c)
    v.SetElementOverrides(e.Id, gSettings)
    return e


def overrideElementDisplay(elements, element_color, level_views):
    errorReport = None
    
    c = convertColor(element_color)
    output = []
    for elem, view in zip(elements, level_views):
        output.append(overrideElementColor(elem, c, view))
    
    return errorReport