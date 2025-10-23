#! python3
# # IMPORT - BASIC PACKAGES 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#
import clr
import os
import json
import shutil

clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
clr.AddReference('UIFrameworkServices')

import revit_script_util
from revit_script_util import Output

from System.Collections.Generic import *

from Autodesk.Revit.DB import Transaction, TransactionGroup, IFCExportOptions, IFCVersion, FilteredElementCollector, View3D
from Autodesk.Revit.DB import SaveAsOptions

from UIFrameworkServices import QuickAccessToolBarService

# IMPORT - CUSTOM FUNCTIONS. 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#
from Tools.ComponentHandlerColumn import ComponentHandlerColumn
from Tools.ComponentHandlerDoor import ComponentHandlerDoor
from Tools.ComponentHandlerSlab import ComponentHandlerSlab
from Tools.ComponentHandlerStair import ComponentHandlerStair
from Tools.ComponentHandlerWall import ComponentHandlerWall

# FUNCTIONS 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#

# CLASS - DesignRevisionExporter: Export the Revit model to IFC and update the data handler.
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class DesignRevisionExporter():

    def __init__(self, doc, path_output, verbose=False):

        self.doc = doc
        
        self.verbose = verbose
        self.path_output = path_output
        self.ifc_version_map = {
            "IFC4": IFCVersion.IFC4,
            "IFC4RV": IFCVersion.IFC4RV,
            "IFC4DTV": IFCVersion.IFC4DTV,
            "IFC2x2": IFCVersion.IFC2x2,
            "IFC2x3": IFCVersion.IFC2x3,
            "IFC2x3CV2": IFCVersion.IFC2x3CV2,
            "IFC2x3BFM": IFCVersion.IFC2x3BFM,
            "IFC2x3FM": IFCVersion.IFC2x3FM,
            "IFCBCA": IFCVersion.IFCBCA,
            "IFCCOBIE": IFCVersion.IFCCOBIE,
            "": IFCVersion.Default
        }

        self._load_file_info()

    def _load_file_info(self):

        self.rvt_filename = self.doc.Title
        self.exp_filename = self.rvt_filename + '.ifc'

        self.rvt_directory_path =  '\\'.join(self.doc.PathName.split('\\')[:-1]) 

    def _load_export_options(self):
        
        self.export_options = {
            "SitePlacement": "3",
            "ExportInternalRevitPropertySets": "true",
            "ExportIFCCommonPropertySets": "true",
            "ExportAnnotations": "true",
            "SpaceBoundaries": "0",
            "ExportRoomsInView": "true",
            "Use2DRoomBoundaryForVolume": "true",
            "UseFamilyAndTypeNameForReference": "true",
            "Export2DElements": "true",
            "ExportPartsAsBuildingElements": "true",
            "ExportBoundingBox": "false",
            "ExportSolidModelRep": "true",
            "ExportSchedulesAsPsets": "false",
            "ExportSpecificSchedules": "false",
            "ExportLinkedFiles": "false",
            "IncludeSiteElevation": "true",
            "StoreIFCGUID": "true",
            "VisibleElementsOfCurrentView": "true",
            "UseActiveViewGeometry": "true",
            "TessellationLevelOfDetail": "1",
            "ExportUserDefinedPsets": "false"
        }

    def ifc_exportation(
        self,
        ifc_version_string="IFC4",
        ):

        self.ifc_version_string = ifc_version_string

        self._load_export_options()

        self._export_ifc_from_active_doc()
        
        msg = "The IFC file has been successfully exported from the design model {}".format(str(self.rvt_filename))
        return msg
    
    def _export_ifc_from_active_doc(self):
        """
        Export IFC from the active Revit document with predefined options.
        Updates the datahandler index and syncs to central if needed.
        """

        all_views = FilteredElementCollector(self.doc).OfClass(View3D).ToElements()
        view3d = next((view for view in all_views if not view.IsTemplate), None)

        if view3d is None:
            if self.verbose:
                print("[Error] No 3D view found in the document.")
            return

        exp_view_id = view3d.Id

        t = Transaction(self.doc, "IFC Export")
        t.Start()

        options = IFCExportOptions()
        options.FileVersion = self.ifc_version_map.get(self.ifc_version_string, IFCVersion.Default)
        options.FilterViewId = exp_view_id
        options.WallAndColumnSplitting = False
        options.ExportBaseQuantities = False

        for key, value in self.export_options.items():
            options.AddOption(key, value)

        try:
            exp_result = self.doc.Export(self.path_output, self.exp_filename, options)
            if self.verbose:
                if exp_result:
                    print("[INFO] IFC Export completed successfully: index = {}".format(self.datahandler['index']))
                else:
                    print("[ERROR] Export failed.")
            t.Commit()

        except Exception as e:
            if self.verbose:
                print("[ERROR] During export:", e)
            t.RollBack()

        finally:
            if self.verbose:
               print("[INFO] IFC Export process completed.")
    
    # =====================================================================================================
    def save_any_time(self, path, revise_label="revise"):

        try:
            # Parse the original path
            dir_path = os.path.dirname(path)
            base_name = os.path.splitext(os.path.basename(path))[0]
            
            # Create revised filename
            revised_filename = "{}-{}.rvt".format(revise_label,base_name)
            revised_path = os.path.join(dir_path, revised_filename)
            
            # Save with revised name
            so = SaveAsOptions()
            so.OverwriteExistingFile = True
            so.Compact = True
            
            self.doc.SaveAs(revised_path, so)
            msg = "The Revit model has been successfully saved to: {}".format(revised_path)
            return msg
            
        except Exception as e:
            msg = "Warning: Failed to save revised model: {}".format(str(e))
            return msg
        
# CLASS - DesignRevisionCore (Main Class for Design Revision Operations)
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
class DesignRevisionCore:
    """
    Central controller for managing all component handlers and executing actions across them.
    """

    def __init__(self, doc, verbose=True):
        
        self.doc = doc
        self.verbose = verbose
        self.todo_design_changes = []  # register first, apply later

        # The full list of building componnet categories..
        # ["ROOF", "WINDOW", "DOOR", "COLUMN", "WALL", "STAIR", "SLAB"]
        # ["ROOF", "WINDOW", "COLUMN", "SLAB"] items are dropped to produce a compact list.
        # = = = >>> ["DOOR", "WALL", "STAIR"]
        
        self.component_handler_map = {
            # ========= "DOOR" =========
            # DOOR	CREATE	Space	CREATE a DOOR in relation to the specified Space
            # DOOR	CREATE	Element	CREATE a DOOR in relation to the specified Element (WALL)
            # ------------------------------------------------------------------------------------------------------
            # DOOR	MODIFY	Space	MODIFY a DOOR in relation to the specified Space
            # DOOR	MODIFY	Element	MODIFY a DOOR in relation to the specified Element (WALL)
            # ------------------------------------------------------------------------------------------------------
            # DOOR	SWAP	Element Family Type	SWAP a DOOR to another DOOR of a different Element Family Type
            # DOOR	SWAP	Element Property	SWAP a DOOR to another DOOR with different Element Properties
            # ------------------------------------------------------------------------------------------------------
            # DOOR	DELETE	Element	DELETE a Element (DOOR)
            # ------------------------------------------------------------------------------------------------------
            "DOOR": ComponentHandlerDoor(self.doc),

            # ========= "WALL" =========
            # WALL	CREATE	Space	CREATE a WALL in relation to the specific Space
            # ------------------------------------------------------------------------------------------------------
            # WALL	MODIFY	Space	MODIFY a WALL in relation to the specified Space
            # ------------------------------------------------------------------------------------------------------
            # WALL	SWAP	Element Family Type	SWAP a WALL to another WALL of a different Element Family Type
            # WALL	SWAP	Element Property	SWAP a WALL to another WALL with different Element Properties
            # ------------------------------------------------------------------------------------------------------
            # WALL	DELETE	Element	DELETE a Element (WALL)
            # ------------------------------------------------------------------------------------------------------
            "WALL": ComponentHandlerWall(self.doc),
            
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
            "STAIR": ComponentHandlerStair(self.doc),
            
            # ========= "COLUMN" ========= ! not implemented.
            "COLUMN": ComponentHandlerColumn(self.doc),
            # ========= "SLAB" ========= ! not implemented.
            "SLAB": ComponentHandlerSlab(self.doc),
        }
        
        self.component_handler_operation_map = {
            "COLUMN": {
                "CREATE": "column_create",
                "MODIFY": "column_modify",
                "SWAP": "column_swap",
                "DELETE": "column_delete"
            },
            "DOOR": {
                "CREATE": "door_create",
                "MODIFY": "door_modify",
                "SWAP": "door_swap",
                "DELETE": "door_delete"
            },
            "SLAB": {
                "CREATE": "slab_create",
                "MODIFY": "slab_modify",
                "SWAP": "slab_swap",
                "DELETE": "slab_delete"
            },
            "STAIR": {
                "CREATE": "stair_create",
                "MODIFY": "stair_modify",
                "SWAP": "stair_swap",
                "DELETE": "stair_delete"
            },
            "WALL": {
                "CREATE": "wall_create",
                "MODIFY": "wall_modify",
                "SWAP": "wall_swap",
                "DELETE": "wall_delete"
            },
        }
    
    def _get_component_handler(self, component_category):
        """
        Retrieve the appropriate handler based on the component category.
        """
        return self.component_handler_map.get(component_category.upper())

    def _get_component_handler_operation(self, component_category, change_operation):
        """
        Get the method name registered for the given category and operation.
        """

        category = component_category.upper()
        operation = change_operation.upper()

        if category not in self.component_handler_operation_map:
            raise ValueError("[ERROR] No handler operation map found for component: {}".format(category))
        if operation not in self.component_handler_operation_map[category]:
            raise ValueError("[ERROR] No operation '{operation}' registered for component: {}".format(category))

        return self.component_handler_operation_map[category][operation]
    
    def register_design_changes(self, action_dict):
        """
        Register a design action for later execution.
        """

        self.todo_design_changes.append(action_dict)        
        if self.verbose:
            Output("[INFO-RevisionCore] Action registered: {} / {}".format(action_dict.get('component_category'), action_dict.get('change_operation')))

    def run_registered_actions(self):
        """
        Apply all registered actions within a transaction group.
        """

        if not self.todo_design_changes:
            if self.verbose:
                Output("[INFO-RevisionCore] No actions to apply.")
            return

        num_changes = len(self.todo_design_changes)

        tg = TransactionGroup(self.doc, "Apply Registered Design Changes")
        tg.Start()
        try:
            for action in self.todo_design_changes:
                self.apply_a_change(action)
            tg.Assimilate()
            if self.verbose:
                Output("[INFO-RevisionCore] All registered design changes applied.")
        except Exception as e:
            tg.RollBack()
            if self.verbose:
                Output("[INFO-RevisionCore] Transaction group failed: {}".format(e))
        
        finally:

            del self.todo_design_changes[:]
            if self.verbose:
                Output("[INFO-RevisionCore] All registered design changes have been released.")
    
        msg = "[INFO-RevisionCore] The registered {} changes have been successfully executed. ".format(str(num_changes))
        return msg
    
    def apply_a_change(self, action_dict):
        """
        Delegates the action to the correct handler and executes the method.
        """

        category = action_dict.get("component_category")
        operation = action_dict.get("change_operation")
        params = action_dict.get("params", {})

        handler = self._get_component_handler(category)
        if not handler:
            if self.verbose:
                Output("[ERROR-RevisionCore] No handler found for component category: {}".format(category))
            return None

        try:
            method_name = self._get_component_handler_operation(category, operation)
            method = getattr(handler, method_name, None)
            if not method:
                if self.verbose:
                    Output("[ERROR-RevisionCore] Handler '{}' has no method named '{}'".format(category, method_name))
                return None

            return method(**params)

        except Exception as e:        
            if self.verbose:
                Output("[ERROR-RevisionCore] Failed to apply action for {}/{}: {}".format(category, operation, e))
            return None
        
    # ====================================================================================================
    # The undo_last_actions method is used to programmatically trigger Revit's internal undo stack.
    # Currently, it's not invovled because we use the Revit Bach Executions.
    def undo_last_actions(self, count=1):
        """
        Programmatically trigger Revit's internal undo stack via QuickAccessToolBarService.
        Args:
            count (int): Number of undo operations to perform.
        """
        
        try:
            # Collect the list of available undo actions (True = undo, False = redo)
            undo_items = QuickAccessToolBarService.collectUndoRedoItems(True)
            
            if undo_items:
                if self.verbose:
                    for idx, item in enumerate(undo_items):
                        print("{}. {}".format(idx + 1, item))
            
            if undo_items and len(undo_items) >= count:
                QuickAccessToolBarService.performMultipleUndoRedoOperations(True, count)
                if self.verbose:
                    print("[INFO] Performed {} undo operation(s).".format(count))
            
            else:
                if self.verbose:
                    print("[INFO] Not enough undo operations available.")
        except Exception as e:
            if self.verbose:
                print("[ERROR] Failed to perform undo: {}".format(e))
        
        finally:
            if self.verbose:
                print("[INFO] The Undo action has been conducted")