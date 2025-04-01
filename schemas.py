import polars as pl
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Tuple
from datetime import date
import traceback
import os

class Octant:
    """Represents a node (octant) in the Octree."""
    def __init__(self, x, y, z, width, depth, height, level=0, max_level=3):
        self.x, self.y, self.z = x, y, z
        self.width, self.depth, self.height = width, depth, height
        self.level = level
        self.max_level = max_level
        self.occupied = False
        self.children = None  # If subdivided, this holds 8 sub-octants

    def subdivide(self):
        """Splits the octant into 8 smaller octants if needed."""
        if self.level >= self.max_level:
            return
        half_w, half_d, half_h = self.width / 2, self.depth / 2, self.height / 2
        self.children = [
            Octant(self.x, self.y, self.z, half_w, half_d, half_h, self.level + 1),
            Octant(self.x + half_w, self.y, self.z, half_w, half_d, half_h, self.level + 1),
            Octant(self.x, self.y + half_d, self.z, half_w, half_d, half_h, self.level + 1),
            Octant(self.x + half_w, self.y + half_d, self.z, half_w, half_d, half_h, self.level + 1),
            Octant(self.x, self.y, self.z + half_h, half_w, half_d, half_h, self.level + 1),
            Octant(self.x + half_w, self.y, self.z + half_h, half_w, half_d, half_h, self.level + 1),
            Octant(self.x, self.y + half_d, self.z + half_h, half_w, half_d, half_h, self.level + 1),
            Octant(self.x + half_w, self.y + half_d, self.z + half_h, half_w, half_d, half_h, self.level + 1),
        ]

    def is_fitting(self, item_row):
        """Checks if an item can fit into this octant."""
        return (
            not self.occupied and 
            item_row["width"] <= self.width and 
            item_row["depth"] <= self.depth and 
            item_row["height"] <= self.height
        )

    def place_item(self, item_row):
        """Tries to place an item into the octree."""
        if self.is_fitting(item_row):
            self.occupied = True
            return pl.DataFrame({
                "start_x": [self.x], "start_y": [self.y], "start_z": [self.z],
                "end_x": [self.x + item_row["width"]],
                "end_y": [self.y + item_row["depth"]],
                "end_z": [self.z + item_row["height"]]
            })  # Returns a DataFrame with placement coordinates

        if not self.children:
            self.subdivide()

        for child in self.children:
            result = child.place_item(item_row)
            if result is not None:
                return result

        return None  # No space found

class Object3D:
    def __init__(self, itemId, name, containerId, start, end):
        self.itemId = itemId
        self.name = name
        self.containerId = containerId
        self.start = start
        self.end = end
        self.front_z = min(start['height'], end['height'])

class Octree:
    """Octree structure for managing storage placement."""
    def __init__(self, container_row):
        self.root = Octant(
            0, 0, 0, container_row["width"], container_row["depth"], container_row["height"]
        )

    def place_item(self, item_row):
        """Finds the best space for an item and places it."""
        return self.root.place_item(item_row)  # Returns DataFrame if placed, None otherwise

class Coordinates(BaseModel):
    width: float
    depth: float
    height: float

class Position(BaseModel):
    startCoordinates: Coordinates
    endCoordinates: Coordinates

class ItemPlacement(BaseModel):
    itemId: int
    containerId: str
    position: Position

class RearrangementStep(BaseModel):
    step: int
    action: str  # "move", "remove", "place"
    itemId: int
    fromContainer: str
    fromPosition: Position
    toContainer: Optional[str] = None
    toPosition: Optional[Position] = None
class Item(BaseModel):
    itemId: int
    name: str
    width: float
    depth: float
    height: float
    priority: int
    expiryDate: Optional[str]  # ISO format date as a string
    usageLimit: int
    preferredZone: str
class Container(BaseModel):
    zone: str
    containerId: str
    width: float
    depth: float
    height: float
class PlacementRequest(BaseModel):
    items: List[Item]
    containers: List[Container]

class PlacementResponse(BaseModel):
    success: bool
    placements: List[ItemPlacement]
    rearrangements: List[RearrangementStep]

class Item_for_search(BaseModel):
    itemId: int
    name: str
    containerId: str  # Where the item is kept
    zone: str  # Zone of the container
    position: Position

# ---------------- Cargo Placement System ----------------

# Modified CargoPlacementSystem class
class CargoPlacementSystem:
    def __init__(self):
        self.items_df = pl.DataFrame()
        self.containers_df = pl.DataFrame()
        self.octrees = {}  # Store octrees separately in a dictionary
        self.loading_log = []  # Added loading_log attribute

    def add_items(self, items: List[dict]):
        """Store items in a Polars DataFrame."""
        self.items_df = pl.DataFrame(items)

    def add_containers(self, containers: List[dict]):
        """Store containers and initialize Octrees using zone."""
        print("\n=== Initializing Containers ===")
        
        try:
            self.containers_df = pl.DataFrame(containers)
            print(f"Added {len(self.containers_df)} containers")
            print(f"Container columns: {self.containers_df.columns}")
        
        # Initialize octrees using the zone
            for container in self.containers_df.iter_rows(named=True):
                try:
                    zone = str(container["zone"]).strip()
                    print(f"\nProcessing container for zone: {zone}")
                    print(f"Container dimensions: {container['width']}x{container['depth']}x{container['height']}")
                    
                    self.octrees[zone] = Octree(container)
                    print(f"Successfully created octree for zone {zone}")
                    
                except Exception as e:
                    print(f"Error creating octree for zone {zone}: {str(e)}")
                    continue
            
            print(f"\nTotal octrees created: {len(self.octrees)}")
            print(f"Zones with octrees: {list(self.octrees.keys())}")
            
        except Exception as e:
            print(f"Error in add_containers: {str(e)}")

            # Initialize octrees using the zone instead of containerId
            for container in self.containers_df.iter_rows(named=True):
                zone = container["zone"].strip()  # Ensure no leading/trailing spaces
                self.octrees[zone] = Octree(container)  # Create and store the octree

    def load_from_csv(self, items_path: str, containers_path: str):
        self.loading_log.append("Loading CSV data...")

        try:
            if os.path.exists(items_path) and os.path.getsize(items_path) > 0:
                self.items_df = pl.read_csv(items_path)
                self.loading_log.append("Items data loaded successfully.")

            if os.path.exists(containers_path) and os.path.getsize(containers_path) > 0:
                self.containers_df = pl.read_csv(containers_path)
                self.loading_log.append("Containers data loaded successfully.")

        except Exception as e:
            self.loading_log.append(f"Error loading data: {str(e)}")
            self.loading_log.append(traceback.format_exc())

    def optimize_placement(self):
        """Places items using Octree, now indexed by zone instead of containerId."""
        print("\n=== Starting Optimization Process ===")
        
        # Debug initial state
        print(f"Items DataFrame Shape: {self.items_df.shape if not self.items_df.is_empty() else 'Empty'}")
        print(f"Containers DataFrame Shape: {self.containers_df.shape if not self.containers_df.is_empty() else 'Empty'}")
        print(f"Number of Octrees: {len(self.octrees)}")
        
        # Validate data frames
        if self.items_df.is_empty() or self.containers_df.is_empty():
            print("Error: No items or containers available.")
            return pl.DataFrame({"success": [False], "placements": [None], "rearrangements": [None]})

        # Validate required columns
        required_item_cols = ["itemId", "width", "depth", "height", "priority", "preferredZone"]
        missing_cols = [col for col in required_item_cols if col not in self.items_df.columns]
        if missing_cols:
            print(f"Error: Missing required columns in items_df: {missing_cols}")
            return pl.DataFrame({"success": [False], "placements": [None], "rearrangements": [None]})

        # Create default placement structure
        default_placements = {
            "itemId": [],
            "zone": [],
            "start_x": [],
            "start_y": [],
            "start_z": [],
            "end_x": [],
            "end_y": [],
            "end_z": []
        }
        placements_df = pl.DataFrame(default_placements)

        # Sort items by priority
        print("\n=== Processing Items ===")
        sorted_items_df = self.items_df.sort("priority", descending=True)
        print(f"Total items to process: {len(sorted_items_df)}")

        # Process each item
        for item_row in sorted_items_df.iter_rows(named=True):
            print(f"\nProcessing item ID: {item_row['itemId']}")
            
            # Validate item data
            try:
                preferred_zone = str(item_row["preferredZone"]).strip()
                print(f"Preferred zone: {preferred_zone}")
                
                # Debug octrees
                print(f"Available zones: {list(self.octrees.keys())}")
                
                # Ensure octrees are properly initialized
                self.octrees = {str(zone).strip(): octree for zone, octree in self.octrees.items()}
                
                octree = self.octrees.get(preferred_zone)
                if octree is None:
                    print(f"Warning: No octree found for zone '{preferred_zone}'")
                    continue

                # Validate item dimensions
                if not all(item_row[dim] > 0 for dim in ['width', 'depth', 'height']):
                    print(f"Warning: Invalid dimensions for item {item_row['itemId']}")
                    continue

                print("Attempting placement...")
                placement_position = octree.place_item(item_row)
                print(f"Placement result: {'Success' if placement_position is not None else 'Failed'}")

                if placement_position is not None:
                    placement_record = pl.DataFrame({
                        "itemId": [item_row["itemId"]],
                        "zone": [preferred_zone],
                    }).hstack(placement_position)

                    placements_df = placements_df.vstack(placement_record) if not placements_df.is_empty() else placement_record
                    print(f"Successfully placed item {item_row['itemId']} in zone {preferred_zone}")
                else:
                    print(f"Failed to place item {item_row['itemId']} in zone {preferred_zone}")

            except Exception as e:
                print(f"Error processing item {item_row['itemId']}: {str(e)}")
                continue

        # Create final result
        print("\n=== Finalizing Results ===")
        print(f"Total successful placements: {len(placements_df)}")
        
        default_rearrangements = {
            "step": [],
            "action": [],
            "itemId": [],
            "fromContainer": [],
            "toContainer": []
        }
        rearrangements_df = pl.DataFrame(default_rearrangements)

        result = pl.DataFrame({
            "success": [True],
            "placements": [placements_df],
            "rearrangements": [rearrangements_df]
        })
        
        print("=== Optimization Complete ===\n")
        return result



# ---------------- Cargo Classification System ----------------
class CargoClassificationSystem:
    def __init__(self):
        self.items_df = pl.DataFrame()
        self.containers_df = pl.DataFrame()
        self.octrees = {}  # Store octrees separately in a dictionary
        self.loading_log = []

    def add_classified_items(self, items: List[dict]):
        """Add classified items to the system using Polars DataFrame."""
        if not items:
            return
        new_df = pl.DataFrame(items)
        self.items_df = self.items_df.vstack(new_df) if not self.items_df.is_empty() else new_df



class TimeSimulationRequest(BaseModel):
    numOfDays: Optional[int] = None
    toTimestamp: Optional[str] = None
    itemsToBeUsedPerDay: List[Dict[str, str]]



# 🚀 **Define Pydantic Model for Item Validation**
class ItemModel(BaseModel):
    itemId: int
    name: str
    width: float
    depth: float
    height: float
    mass: float
    priority: int
    expiryDate: Optional[date] = None  # Optional since expiry can be null
    usageLimit: int
    preferredZone: str

# 🚀 **Define Pydantic Model for Container Validation**
class ContainerModel(BaseModel):
    zone: str
    containerId: int
    width: float
    depth: float
    height: float

class ImportItemsResponse(BaseModel):
    success: bool
    itemsImported: int
    errors: Optional[List[dict]] = []
    message: str

class ImportContainersResponse(BaseModel):
    success: bool
    containersImported: int
    errors: Optional[List[dict]] = []
    message: str

class CargoArrangementExport(BaseModel):
    """Schema for exporting cargo arrangement as CSV."""
    itemId: int
    containerId: str
    position: Coordinates

class RetrieveItemRequest(BaseModel):
    itemId: int = Field(..., description="Unique identifier for the item to retrieve")
    userId: str = Field(..., description="ID of the user retrieving the item")
    timestamp: Optional[str] = Field(None, description="Timestamp of retrieval (ISO format)")

class RetrievalStep(BaseModel):
    step: int
    action: str
    itemId: int
    itemName: str

class SearchResponse(BaseModel):
    success: bool
    found: bool
    item: Optional[Item_for_search] = None
    retrievalSteps: List[RetrievalStep] = []

class PlaceItemRequest(BaseModel):
    itemId: int = Field(..., description="Unique identifier for the item")
    userId: str = Field(..., description="ID of the user placing the item")
    timestamp: Optional[str] = Field(None, description="Timestamp of placement (ISO format)")
    containerId: str = Field(..., description="Container where the item is kept")
    position: Position = Field(..., description="Position coordinates of the item")

class PlaceItemResponse(BaseModel):
    success: bool

class ReturnPlanRequest(BaseModel):
    undockingContainerId: str
    undockingDate: str
    maxWeight: float

# Complete Undocking
class CompleteUndockingRequest(BaseModel):
    undockingContainerId: str
    timestamp: str

class WasteItem(BaseModel):
    itemId: int
    name: str
    reason: str
    containerId: str
    position: Position

class WasteItemResponse(BaseModel):
    success: bool
    wasteItems: List[WasteItem] = []

class WasteItemRequest(BaseModel):
    itemId: int
    name: str
    reason: str
    containerId: str
    position: str

class CompleteUndockingRequest(BaseModel):
    undockingContainerId: str
    timestamp: str

class ReturnPlanStep(BaseModel):
    step: int
    itemId: int
    itemName: str
    fromContainer: str
    toContainer: str


class ReturnItem(BaseModel):
    itemId: int
    name: str
    reason: str

class ReturnManifest(BaseModel):
    undockingContainerId: str
    undockingDate: str
    returnItems: List[ReturnItem]
    totalVolume: float
    totalWeight: float

class ReturnPlanResponse(BaseModel):
    success: bool
    returnPlan: List[ReturnPlanStep]
    retrievalSteps: List[RetrievalStep]
    returnManifest: ReturnManifest




