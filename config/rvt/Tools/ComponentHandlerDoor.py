#! python3
# # IMPORT - BASIC PACKAGES 
# =====================================================================================================
# =====================================================================================================
# =====================================================================================================
#
import clr

import revit_script_util
from revit_script_util import Output

clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
from System.Collections.Generic import *
from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.DB import Transaction, BuiltInCategory, ElementId
from Autodesk.Revit.DB import Structure, FamilyInstance, LocationPoint

# =====================================================================================================
# IMPORT - REVIT Batch UTILITIES
import revit_script_util
from revit_script_util import Output

# =====================================================================================================
# IMPORT - CUSTOM FUNCTIONS. 
from Tools.ComponentHandlerBase import NoWarningsFailurePreprocessor, ComponentHandlerBase

# =====================================================================================================
# CLASS - ComponentHandlerDoor (Subclass)
# ========= "DOOR" =========
# DOOR	CREATE	Space	CREATE a DOOR in relation to the specified Space
# DOOR	CREATE	Element	CREATE a DOOR in relation to the specified Element (WALL)
# ----> door_creation(self, ref_door_id, ref_room_id, ref_wall_id)
# ------------------------------------------------------------------------------------------------------
# DOOR	MODIFY	Space	MODIFY a DOOR in relation to the specified Space
# DOOR	MODIFY	Element	MODIFY a DOOR in relation to the specified Element (WALL)
# ----> door_modification(self, ref_door_id, ref_room_id, ref_wall_id)
# ------------------------------------------------------------------------------------------------------
# DOOR	SWAP	Element Family Type	SWAP a DOOR to another DOOR of a different Element Family Type
# DOOR	SWAP	Element Property	SWAP a DOOR to another DOOR with different Element Properties
# ------------------------------------------------------------------------------------------------------
# DOOR	DELETE	Element	DELETE a Element (DOOR)
# ----> door_deletion(self, ref_door_id)
# ------------------------------------------------------------------------------------------------------
class ComponentHandlerDoor(ComponentHandlerBase):
    """
    Handler class for door creation and revision logic.
    main functions: 
    - door_movement_along_wall_within_room:     moves a door along the wall within the room's projection scope.
    - create_door_on_wall_within_room:        creates a door on the wall within the room's projection scope.
    """
    def __init__(self, doc):
        
        self.doc = doc
        self._get_sorted_levels(doc)

        self.default_reference_component_id = self._get_default_reference_component_id(doc, BuiltInCategory.OST_Doors)
        
    # ================================================
    # ================================================
    # ================================================
    # ================  C R E A T E  =================
    # ================================================
    # ================================================
    # ================================================
    def door_create(
        self,
        ref_room_id,
        ref_wall_id,
        ref_door_id=None,
        params_door_create=0, # 0=center, 1=side1, 2=side2):
        ):
        """
        # DOOR	CREATE	Space	        CREATE a DOOR in relation to the specified Space
        # DOOR	CREATE	Element	        CREATE a DOOR in relation to the specified Element (WALL)

        ref_door_id:
            count the number of doors in the project, and use the one that is most frequently used via '_count_element_types_by_category'
        ref_room_id: 
            if given, use the given room;
            if not given, use one of the rooms that are connected to the wall.
        ref_wall_id:
            if given, use the given wall;
            if not given, use one of the walls that are bounded around the room.
        """

        # get the default component as reference for creation.
        ref_door_id = self.default_reference_component_id if ref_door_id == None else ref_door_id
        ref_door = self.doc.GetElement(ref_door_id)
        if not ref_door:
            Output("[ERROR-HandlerDoor] Invalid reference door ID.")
            return None
        ref_door_type = self.doc.GetElement(ref_door.GetTypeId())

        room = self.doc.GetElement(ref_room_id)
        wall = self.doc.GetElement(ref_wall_id)
        
        return self._create_door_on_wall_within_room(
            room=room,
            wall=wall,
            door_type=ref_door_type,
            location_index=params_door_create,)
    
    def _create_door_on_wall_within_room(
        self,
        room,
        wall,
        location_index=0, # 0=center, 1=side1, 2=side2
        room_bdry_edge_in_feet=0.65, # on feet
        door_type=None,
        level=None):
        """
        Places a door at the midpoint of a wall.
        The door is placed at the center of the wall, and the door type and level can be specified.
        location_index = 0 means the center of the wall ;
        location_index = 1 means one side of the wall (side of the room);
        location_index = 2 means another side of the wall (side of the room);
        ------------------------------------------------------
        BUG:    This function does not work well for irregular rooms:
                Cases where the walls are not aligned with the space boundaries.
        ------------------------------------------------------
        """
        
        self.room_bdry_edge = room_bdry_edge_in_feet*3.28084
        level = self.doc.GetElement(wall.LevelId)

        if not door_type:
            raise ValueError("[ERROR] No door type provided.")
            # door_type = FilteredElementCollector(self.doc)\
            #     .OfCategory(BuiltInCategory.OST_Doors)\
            #     .WhereElementIsElementType()\
            #     .FirstElement()

        placement_point = self._get_room_relevant_wall_placement_point(
            room, wall, location_index=location_index)

        if not door_type.IsActive:
            t = Transaction(self.doc, "Activate Door Type")
            t.Start()
            door_type.Activate()
            t.Commit()

        t = Transaction(self.doc, "Insert the Door")
        
        options = t.GetFailureHandlingOptions()
        options.SetFailuresPreprocessor(NoWarningsFailurePreprocessor())
        t.SetFailureHandlingOptions(options)
        
        t.Start()
        try:
            door = self.doc.Create.NewFamilyInstance(placement_point, door_type, wall, level, Structure.StructuralType.NonStructural)
            t.Commit()
            Output("[INFO-HandlerDoor] Door created successfully.")

            return door
        except Exception as e:
            Output("[ERROR-HandlerDoor] Failed to place door")
            t.RollBack()
        
    # ================================================
    # ================================================
    # ================================================
    # ================  M O D I F Y  =================
    # ================================================
    # ================================================
    # ================================================
    def door_modify(
        self,
        ref_room_id,
        ref_wall_id,
        ref_door_id,
        params_door_modify=0, # 0=center, 1=side1, 2=side2):
        ):
        """
        # DOOR	MODIFY	Space	        MODIFY a DOOR in relation to the specified Space
        # DOOR	MODIFY	Element	        MODIFY a DOOR in relation to the specified Element (WALL)
        """

        door = self.doc.GetElement(ref_door_id)
        room = self.doc.GetElement(ref_room_id)
        wall = self.doc.GetElement(ref_wall_id)

        return self._modify_door_along_wall_within_room(
            door=door,
            wall=wall,
            room=room,
            location_index=params_door_modify,
        )
    
    def _modify_door_along_wall_within_room(
        self,
        door,
        wall,
        room,
        location_index=1, # 0=center, 1=side1, 2=side2
        room_bdry_edge_in_feet =0.65, # on feet
        ):

        """
        Moves a door along the host wall, constrained within the room's projection scope.
        Parameters:
            door (FamilyInstance): The door to move.
            wall (Wall): The wall to move along.
            room (Room): Room that defines the target scope.
            location_index = 0 means the center of the wall ;
            location_index = 1 means one side of the wall (side of the room);
            location_index = 2 means another side of the wall (side of the room);
        -------------------------------------------------------
        BUG: This fucntion is to be tested for more complex cases.
        -------------------------------------------------------
        """

        self.room_bdry_edge = room_bdry_edge_in_feet*3.28084

        if not isinstance(door, FamilyInstance):
            Output("[ERROR-HandlerDoor] Provided element is not a FamilyInstance.")
            return
        if not wall or not hasattr(wall.Location, "Curve"):
            Output("[ERROR-HandlerDoor] Wall does not have valid geometry.")
            return

        # Step 1 - Get room feature points
        placement_point = self._get_room_relevant_wall_placement_point(
            room, wall, location_index=location_index)
        
        if not placement_point:
            Output("[ERROR-HandlerDoor] Placement point could not be computed.")
            return

        door_loc = door.Location
        if not isinstance(door_loc, LocationPoint):
            Output("[ERROR-HandlerDoor] Door location is not a point location.")
            return

        move_vec = placement_point.Subtract(door_loc.Point)
        # print ("[DEBUG] Move vector:", move_vec)
        
        t = Transaction(self.doc, "Move Door Within Room Scope")
        
        options = t.GetFailureHandlingOptions()
        options.SetFailuresPreprocessor(NoWarningsFailurePreprocessor())
        t.SetFailureHandlingOptions(options)
        
        t.Start()
        try:
            door_loc.Move(move_vec)
            t.Commit()
            Output("[INFO-HandlerDoor] Door moved.")
        except Exception as e:
            Output("[ERROR-HandlerDoor] Failed to move door.")
            t.RollBack()

    # ================================================
    # ================================================
    # ================================================
    # ================  D E L E T E  =================
    # ================================================
    # ================================================
    # ================================================
    def door_delete(self, ref_door_id):
        """
        # DOOR	DELETE	        Element	DELETE a Element (DOOR)
        """
        if isinstance(ref_door_id, int):
            ref_door_id = ElementId(ref_door_id)
        ref_door = self.doc.GetElement(ref_door_id)

        if not ref_door:
            print("[ERROR] Door element not found.")
            return False

        try:
            t = Transaction(self.doc, "Delete Door")
            t.Start()
            self.doc.Delete(ref_door.Id)
            t.Commit()
            Output("[INFO] Door deleted.")
            return True
        except Exception as e:
            Output("[ERROR] Failed to delete door.")
            if t.HasStarted():
                t.RollBack()
            return False
    
    # ================================================
    # ================================================
    # ================================================
    # ================  S  W  A  P  ==================
    # ================================================
    # ================================================
    # ================================================
    # 

    