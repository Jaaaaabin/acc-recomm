# ==================================================
# PYREVIT + REVIT API BOILERPLATE
# ==================================================
import clr
import System
import os
import sys
import json

# Add project root to Python path for common modules
project_root = r"H:\dev\acc-recomm\acc-recomm"

python_src_path = os.path.join(project_root, "src")
if python_src_path not in sys.path:
    sys.path.insert(0, python_src_path)

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector, FamilySymbol, FamilyInstance, ElementId

import revit_script_util
from revit_script_util import Output

sessionId = revit_script_util.GetSessionId()
uiapp = revit_script_util.GetUIApplication()
doc = revit_script_util.GetScriptDocument()
revitFilePath = revit_script_util.GetRevitFilePath()
revitFileName = os.path.basename(revitFilePath).replace('.rvt', '')  # used as key

# ==================================================
# LOGGING UTIL
# ==================================================
# Initialize logger

def log_separator(msg=None):
    separator = "=" * 55
    Output(separator)
    if msg:
        Output(msg)

def make_directory(path):
    """
    Create a directory if it does not exist.
    """
    if not os.path.exists(path):
        os.makedirs(path)
        msg = "Created directory: {}".format(path)
        Output(msg)
    else:
        msg = "Using existing directory: {}".format(path)
        Output(msg)
        
# ==================================================
# SETUP PATHS
# ==================================================
# Initialize path manager
path_lib = os.path.join(project_root, "config", "rvt")
if str(path_lib) not in sys.path:
    sys.path.append(str(path_lib))

# Get data paths using systematic path management
path_data_processed = os.path.join(project_root, 'data', 'processed')
path_data_processed_ifc = os.path.join(path_data_processed, 'ifc')
path_data_processed_ifc_byfile = os.path.join(path_data_processed_ifc, revitFileName)
make_directory(path_data_processed_ifc_byfile)

path_data_processed_rvt = os.path.join(path_data_processed, 'rvt')
path_data_processed_rvt_byfile = os.path.join(path_data_processed_rvt, revitFileName)
make_directory(path_data_processed_rvt_byfile)
# ==================================================
# LOAD CUSTOM MODULES
# ==================================================
try:
    from Tools.DesignRevisionCore import DesignRevisionExporter
    from Tools.BuildingComponentDependency import ComponentDependencyExtractor
    log_separator("Custom modules imported successfully.")
except ImportError as e:
    error_msg = "Failed to import custom modules: {}".format(e)
    log_separator(error_msg)
    raise

# ==================================================
# EXPORT IFC
# ==================================================
try:
    exporter = DesignRevisionExporter(doc, str(path_data_processed_ifc_byfile), verbose=False)
    msg_ifc_exporter = exporter.ifc_exportation(ifc_version_string="IFC4")
    log_separator(msg_ifc_exporter)
except Exception as e:
    error_msg = "IFC export failed: {}".format(e)
    log_separator(error_msg)
    raise

# ==================================================
# GENERATE AND SAVE COMPONENT INSTANCES
# ==================================================
try:
    extractor = ComponentDependencyExtractor(doc, str(path_data_processed_rvt_byfile))
    extractor.generate_and_save_instances()
    log_separator("ComponentDependencyExtractor - instances extracted.")
    extractor.construct_and_save_relationships()
    log_separator("ComponentDependencyExtractor - relationship extracted.")
except Exception as e:
    error_msg = "ComponentDependencyExtractor failed: {}".format(e)
    log_separator(error_msg)
    raise

# Final completion message
completion_msg = "RvtBatch execution completed successfully!"
log_separator(completion_msg)