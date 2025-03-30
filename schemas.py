import polars as pl
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import date

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
    itemId: str
    containerId: str
    position: Position

class RearrangementStep(BaseModel):
    step: int
    action: str  # "move", "remove", "place"
    itemId: str
    fromContainer: str
    fromPosition: Position
    toContainer: Optional[str] = None
    toPosition: Optional[Position] = None
class Item(BaseModel):
    itemId: str
    name: str
    width: float
    depth: float
    height: float
    priority: int
    expiryDate: Optional[str]  # ISO format date as a string
    usageLimit: int
    preferredZone: str
class Container(BaseModel):
    containerId: str
    zone: str
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

# ---------------- Cargo Placement System ----------------

class CargoPlacementSystem:
    def __init__(self):
        self.items_df = pl.DataFrame()
        self.containers_df = pl.DataFrame()

        # Modify octree storage to use `zone` instead of `containerId`
        self.octrees = pl.DataFrame({
            "zone": [],
            "octree": []
        })

    def add_items(self, items: List[dict]):
        """Store items in a Polars DataFrame."""
        self.items_df = pl.DataFrame(items)

    def add_containers(self, containers: List[dict]):
        """Store containers and initialize Octrees using zone."""
        self.containers_df = pl.DataFrame(containers)

        print("=== Containers DataFrame ===")
        print(self.containers_df)

        # Keep existing container import code
        self.octrees = {}  # Store octrees separately in a dictionary

        # Initialize octrees using the zone instead of containerId
        for container in self.containers_df.iter_rows(named=True):
            zone = container["zone"]  # Use zone as the key
            self.octrees[zone] = Octree(container)  # Create and store the octree

        print("=== Initialized Octrees ===")
        print(self.octrees)


    def optimize_placement(self):
        """Places items using Octree, now indexed by zone instead of containerId."""
        placements_df = pl.DataFrame()
        rearrangements_df = pl.DataFrame()

        if self.items_df.is_empty() or self.containers_df.is_empty():
            print("Error: No items or containers available.")
            return pl.DataFrame({"success": [False], "placements": [None], "rearrangements": [None]})

        sorted_items_df = self.items_df.sort("priority", descending=True)

        for item_row in sorted_items_df.iter_rows(named=True):
            preferred_zone = item_row["preferredZone"].strip()  # Ensure no leading/trailing spaces

            # Ensure stored octrees also have trimmed keys
            self.octrees = {zone.strip(): octree for zone, octree in self.octrees.items()}  

            octree = self.octrees.get(preferred_zone)  # Lookup with trimmed zone

            if octree is None:
                print(f"Warning: No octree found for zone '{preferred_zone}'")
                continue

            placement_position = octree.place_item(item_row)

            if placement_position is not None:
                placement_record = pl.DataFrame({
                    "itemId": [item_row["itemId"]],
                    "zone": [preferred_zone],  # Store zone instead of containerId
                }).hstack(placement_position)

                placements_df = placements_df.vstack(placement_record) if not placements_df.is_empty() else placement_record
            else:
                print(f"Failed to place item {item_row['itemId']} in zone {preferred_zone}")

        return pl.DataFrame({
            "success": [True],
            "placements": [placements_df],
            "rearrangements": [rearrangements_df]
        })




# ---------------- Cargo Classification System ----------------
class CargoClassificationSystem:
    def __init__(self):
        self.items_df = pl.DataFrame()

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
    containerId: int
    zone: str
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

class Coordinates(BaseModel):
    """Represents the start and end coordinates of an item placement."""
    start_x: float
    start_y: float
    start_z: float
    end_x: float
    end_y: float
    end_z: float


class CargoArrangementExport(BaseModel):
    """Schema for exporting cargo arrangement as CSV."""
    itemId: str
    containerId: str
    position: Coordinates
