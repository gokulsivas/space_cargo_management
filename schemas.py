import polars as pl
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Tuple
from datetime import date
import traceback
import os

class Octant:
    """Represents a node (octant) in the Octree."""
    def __init__(self, x, y, z, width_cm, depth_cm, height_cm, level=0, max_level=3):
        self.x, self.y, self.z = x, y, z
        self.width_cm, self.depth_cm, self.height_cm = width_cm, depth_cm, height_cm
        self.level = level
        self.max_level = max_level
        self.occupied = False
        self.children = None  # If subdivided, this holds 8 sub-octants

    def subdivide(self):
        """Splits the octant into 8 smaller octants if needed."""
        if self.level >= self.max_level:
            return
        half_w, half_d, half_h = self.width_cm / 2, self.depth_cm / 2, self.height_cm / 2
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
            item_row["width_cm"] <= self.width_cm and 
            item_row["depth_cm"] <= self.depth_cm and 
            item_row["height_cm"] <= self.height_cm
        )

    def place_item(self, item_row):
        """Tries to place an item into the octree."""
        if self.is_fitting(item_row):
            self.occupied = True
            return pl.DataFrame({
                "start_x": [self.x], "start_y": [self.y], "start_z": [self.z],
                "end_x": [self.x + item_row["width_cm"]],
                "end_y": [self.y + item_row["depth_cm"]],
                "end_z": [self.z + item_row["height_cm"]]
            })

        if not self.children:
            self.subdivide()

        for child in self.children:
            result = child.place_item(item_row)
            if result is not None:
                return result

        return None  # No space found

class Object3D:
    def __init__(self, item_id, name, container_id, start, end):
        self.item_id = item_id
        self.name = name
        self.container_id = container_id
        self.start = start
        self.end = end
        self.front_z = min(start['height_cm'], end['height_cm'])

class Octree:
    """Octree structure for managing storage placement."""
    def __init__(self, container_row):
        self.root = Octant(
            0, 0, 0, container_row["width_cm"], container_row["depth_cm"], container_row["height_cm"]
        )

    def place_item(self, item_row):
        """Finds the best space for an item and places it."""
        return self.root.place_item(item_row)

class Coordinates(BaseModel):
    width_cm: float
    depth_cm: float
    height_cm: float

class Position(BaseModel):
    startCoordinates: Coordinates
    endCoordinates: Coordinates

class ItemPlacement(BaseModel):
    item_id: int
    container_id: str
    position: Position

class RearrangementStep(BaseModel):
    step: int
    action: str  # "move", "remove", "place"
    item_id: int
    from_container: str
    from_position: Position
    to_container: Optional[str] = None
    to_position: Optional[Position] = None

from pydantic import BaseModel, Field

class Item(BaseModel):
    item_id: int
    name: str
    width_cm: int
    depth_cm: int
    height_cm: int
    mass_kg: float
    priority: int
    preferred_zone: str
    expiry_date: Optional[str] = None
    usage_limit: Optional[int] = None


class Container(BaseModel):
    container_id: str
    zone: str
    width_cm: float
    depth_cm: float
    height_cm: float

class PlacementRequest(BaseModel):
    items: List[Item]
    containers: List[Container]

class PlacementResponse(BaseModel):
    success: bool
    placements: List[ItemPlacement]
    rearrangements: List[RearrangementStep]

class Item_for_search(BaseModel):
    item_id: int
    name: str
    container_id: str
    zone: str
    position: Position

class CargoPlacementSystem:
    def __init__(self):
        self.items_df = pl.DataFrame()
        self.containers_df = pl.DataFrame()
        self.octrees = {}
        self.loading_log = []

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
        
            for container in self.containers_df.iter_rows(named=True):
                try:
                    zone = str(container["zone"]).strip()
                    print(f"\nProcessing container for zone: {zone}")
                    print(f"Container dimensions: {container['width_cm']}x{container['depth_cm']}x{container['height_cm']}")
                    
                    self.octrees[zone] = Octree(container)
                    print(f"Successfully created octree for zone {zone}")
                    
                except Exception as e:
                    print(f"Error creating octree for zone {zone}: {str(e)}")
                    continue
            
            print(f"\nTotal octrees created: {len(self.octrees)}")
            print(f"Zones with octrees: {list(self.octrees.keys())}")
            
        except Exception as e:
            print(f"Error in add_containers: {str(e)}")

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
        """Places items using Octree, now indexed by zone."""
        print("\n=== Starting Optimization Process ===")
        
        print(f"Items DataFrame Shape: {self.items_df.shape if not self.items_df.is_empty() else 'Empty'}")
        print(f"Containers DataFrame Shape: {self.containers_df.shape if not self.containers_df.is_empty() else 'Empty'}")
        print(f"Number of Octrees: {len(self.octrees)}")
        
        if self.items_df.is_empty() or self.containers_df.is_empty():
            print("Error: No items or containers available.")
            return pl.DataFrame({"success": [False], "placements": [None], "rearrangements": [None]})

        required_item_cols = ["item_id", "width_cm", "depth_cm", "height_cm", "priority", "preferred_zone"]
        missing_cols = [col for col in required_item_cols if col not in self.items_df.columns]
        if missing_cols:
            print(f"Error: Missing required columns in items_df: {missing_cols}")
            return pl.DataFrame({"success": [False], "placements": [None], "rearrangements": [None]})

        default_placements = {
            "item_id": [],
            "zone": [],
            "start_x": [],
            "start_y": [],
            "start_z": [],
            "end_x": [],
            "end_y": [],
            "end_z": []
        }
        placements_df = pl.DataFrame(default_placements)

        print("\n=== Processing Items ===")
        sorted_items_df = self.items_df.sort("priority", descending=True)
        print(f"Total items to process: {len(sorted_items_df)}")

        for item_row in sorted_items_df.iter_rows(named=True):
            print(f"\nProcessing item ID: {item_row['item_id']}")
            
            try:
                preferred_zone = str(item_row["preferred_zone"]).strip()
                print(f"Preferred zone: {preferred_zone}")
                
                print(f"Available zones: {list(self.octrees.keys())}")
                
                self.octrees = {str(zone).strip(): octree for zone, octree in self.octrees.items()}
                
                octree = self.octrees.get(preferred_zone)
                if octree is None:
                    print(f"Warning: No octree found for zone '{preferred_zone}'")
                    continue

                if not all(item_row[dim] > 0 for dim in ['width_cm', 'depth_cm', 'height_cm']):
                    print(f"Warning: Invalid dimensions for item {item_row['item_id']}")
                    continue

                print("Attempting placement...")
                placement_position = octree.place_item(item_row)
                print(f"Placement result: {'Success' if placement_position is not None else 'Failed'}")

                if placement_position is not None:
                    placement_record = pl.DataFrame({
                        "item_id": [item_row["item_id"]],
                        "zone": [preferred_zone],
                    }).hstack(placement_position)

                    placements_df = placements_df.vstack(placement_record) if not placements_df.is_empty() else placement_record
                    print(f"Successfully placed item {item_row['item_id']} in zone {preferred_zone}")
                else:
                    print(f"Failed to place item {item_row['item_id']} in zone {preferred_zone}")

            except Exception as e:
                print(f"Error processing item {item_row['item_id']}: {str(e)}")
                continue

        print("\n=== Finalizing Results ===")
        print(f"Total successful placements: {len(placements_df)}")
        
        default_rearrangements = {
            "step": [],
            "action": [],
            "item_id": [],
            "from_container": [],
            "to_container": []
        }
        rearrangements_df = pl.DataFrame(default_rearrangements)

        result = pl.DataFrame({
            "success": [True],
            "placements": [placements_df],
            "rearrangements": [rearrangements_df]
        })
        
        print("=== Optimization Complete ===\n")
        return result

class CargoClassificationSystem:
    def __init__(self):
        self.items_df = pl.DataFrame()
        self.containers_df = pl.DataFrame()
        self.octrees = {}
        self.loading_log = []

    def add_classified_items(self, items: List[dict]):
        if not items:
            return
        new_df = pl.DataFrame(items)
        self.items_df = self.items_df.vstack(new_df) if not self.items_df.is_empty() else new_df

class TimeSimulationRequest(BaseModel):
    num_of_days: Optional[int] = None
    to_timestamp: Optional[str] = None
    items_to_be_used_per_day: List[Dict[str, str]]

class ItemModel(BaseModel):
    item_id: int
    name: str
    width_cm: float
    depth_cm: float
    height_cm: float
    mass_kg: float
    priority: int
    expiry_date: Optional[date] = None
    usage_limit: int
    preferred_zone: str

class ContainerModel(BaseModel):
    zone: str
    container_id: int
    width_cm: float
    depth_cm: float
    height_cm: float

class ImportItemsResponse(BaseModel):
    success: bool
    items_imported: int
    errors: Optional[List[dict]] = []
    message: str

class ImportContainersResponse(BaseModel):
    success: bool
    containers_imported: int
    errors: Optional[List[dict]] = []
    message: str

class CargoArrangementExport(BaseModel):
    item_id: int
    container_id: str
    position: Coordinates

class RetrieveItemRequest(BaseModel):
    item_id: int
    user_id: str
    timestamp: Optional[str] = None

class RetrievalStep(BaseModel):
    step: int
    action: str  # "remove", "setAside", "retrieve", "placeBack"
    item_id: int
    item_name: str

class SearchResponse(BaseModel):
    success: bool
    found: bool
    item: Optional[Item_for_search] = None
    retrieval_steps: List[RetrievalStep] = []

class PlaceItemRequest(BaseModel):
    item_id: int
    container_id: str
    position: Position
    timestamp: Optional[str] = None

class PlaceItemResponse(BaseModel):
    success: bool

class ReturnPlanRequest(BaseModel):
    undocking_container_id: str
    undocking_date: str
    max_weight: float
    user_id: str

class CompleteUndockingRequest(BaseModel):
    undocking_container_id: str
    timestamp: str
    user_id: str

class WasteItem(BaseModel):
    item_id: int
    name: str
    reason: str
    container_id: str
    position: Position

class WasteItemResponse(BaseModel):
    success: bool
    waste_items: List[WasteItem] = []

class WasteItemRequest(BaseModel):
    item_id: int
    name: str
    reason: str
    container_id: str
    position: str

class ReturnPlanStep(BaseModel):
    step: int
    item_id: str
    item_name: str
    from_container: str
    to_container: str

class ReturnItem(BaseModel):
    item_id: str
    name: str
    reason: str

class ReturnManifest(BaseModel):
    undocking_container_id: str
    undocking_date: str
    return_items: List[ReturnItem]
    total_volume: float
    total_weight: float

class ReturnPlanResponse(BaseModel):
    success: bool
    return_plan: List[ReturnPlanStep]
    retrieval_steps: List[RetrievalStep]
    return_manifest: ReturnManifest