from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Tuple, Union
import numpy as np
from datetime import datetime
import polars as pl
import csv
from collections import defaultdict

@dataclass
class OctreeNode:
    center: np.ndarray
    size: float
    children: List['OctreeNode']
    occupied: bool = False
    item_id: Optional[str] = None
    rotation: Optional[str] = None
    priority: Optional[int] = None
    depth: int = 0

@dataclass
class Position3D:
    x: int
    y: int
    z: int

@dataclass
class ItemDimensions:
    width_cm: float
    depth_cm: float
    height_cm: float
    priority: int
    mass_kg: float = 0
    item_id: Optional[Union[str, int]] = None

class Rotation(Enum):
    NO_ROTATION = "NO_ROTATION"
    ROTATE_X = "ROTATE_X"
    ROTATE_Y = "ROTATE_Y"
    ROTATE_Z = "ROTATE_Z"

def load_csv(filename):
    """Load CSV data efficiently using Polars"""
    try:
        return pl.read_csv(filename).to_dicts()
    except Exception as e:
        print(f"Error loading CSV {filename}: {str(e)}")
        return {}

class SparseMatrix:
    """Sparse 3D matrix implementation for memory efficiency"""
    def __init__(self, width_cm, depth_cm, height_cm):
        self.width_cm = int(width_cm)
        self.depth_cm = int(depth_cm)
        self.height_cm = int(height_cm)
        self.occupied_cells = set()  # Store only occupied coordinates

    def is_occupied(self, x_start, y_start, z_start, x_end, y_end, z_end):
        """Check if any cell in the region is occupied"""
        for x in range(x_start, x_end):
            for y in range(y_start, y_end):
                for z in range(z_start, z_end):
                    if (x, y, z) in self.occupied_cells:
                        return True
        return False

    def occupy(self, x_start, y_start, z_start, x_end, y_end, z_end):
        """Mark a region as occupied"""
        for x in range(x_start, x_end):
            for y in range(y_start, y_end):
                for z in range(z_start, z_end):
                    self.occupied_cells.add((x, y, z))

class SpaceOctree:
    def __init__(self, center: np.ndarray, size: float, max_depth: int = 5):
        self.root = OctreeNode(center, size, [])
        self.max_depth = max_depth
        self.item_nodes = {}  # Maps item_ids to their nodes
        # Add spatial hash for faster neighbor finding
        self.spatial_hash = defaultdict(list)  # Maps grid cells to items
        self.grid_size = size / 8  # Grid cell size

    def subdivide(self, node: OctreeNode) -> None:
        half_size = node.size / 2
        offsets = [
            np.array([-1, -1, -1]), np.array([1, -1, -1]),
            np.array([-1, 1, -1]), np.array([1, 1, -1]),
            np.array([-1, -1, 1]), np.array([1, -1, 1]),
            np.array([-1, 1, 1]), np.array([1, 1, 1])
        ]
        
        for offset in offsets:
            child_center = node.center + (offset * half_size/2)
            child = OctreeNode(child_center, half_size, [], depth=node.depth + 1)
            node.children.append(child)

    def insert_item(self, item_id: Union[str, int], position: Dict, rotation: str, priority: int) -> bool:
        # Convert item_id to string for consistency
        item_id_str = str(item_id)
        
        start = np.array([
            position["startCoordinates"]["width_cm"],
            position["startCoordinates"]["depth_cm"],
            position["startCoordinates"]["height_cm"]
        ])
        end = np.array([
            position["endCoordinates"]["width_cm"],
            position["endCoordinates"]["depth_cm"],
            position["endCoordinates"]["height_cm"]
        ])
        
        success = self._insert_recursive(self.root, start, end, item_id_str, rotation, priority)
        if success:
            node = self._find_node(item_id_str)
            self.item_nodes[item_id_str] = node
            
            # Add to spatial hash for faster neighbor finding
            self._add_to_spatial_hash(item_id_str, start, end)
        return success

    def _add_to_spatial_hash(self, item_id: str, start: np.ndarray, end: np.ndarray):
        """Add item to spatial hash for faster neighbor lookups"""
        # Calculate grid cells that this item occupies
        start_cell = (int(start[0] // self.grid_size), 
                     int(start[1] // self.grid_size), 
                     int(start[2] // self.grid_size))
        end_cell = (int(end[0] // self.grid_size) + 1, 
                   int(end[1] // self.grid_size) + 1, 
                   int(end[2] // self.grid_size) + 1)
        
        # Add item to all cells it intersects
        for x in range(start_cell[0], end_cell[0]):
            for y in range(start_cell[1], end_cell[1]):
                for z in range(start_cell[2], end_cell[2]):
                    self.spatial_hash[(x, y, z)].append(item_id)

    def _insert_recursive(self, node: OctreeNode, start: np.ndarray, end: np.ndarray, 
                       item_id: str, rotation: str, priority: int) -> bool:
        if node.occupied:
            return False

        node_min = node.center - node.size/2
        node_max = node.center + node.size/2

        # Check if item fits in this node
        if not self._bounds_overlap(start, end, node_min, node_max):
            return False

        # If node perfectly fits the item
        if self._bounds_similar(start, end, node_min, node_max):
            node.occupied = True
            node.item_id = item_id
            node.rotation = rotation
            node.priority = priority
            return True

        # Otherwise, try subdividing if possible
        if not node.children and node.depth < self.max_depth:
            self.subdivide(node)

        # Try inserting into children
        if node.children:
            for child in node.children:
                if self._insert_recursive(child, start, end, item_id, rotation, priority):
                    return True

        return False

    def _bounds_overlap(self, min1: np.ndarray, max1: np.ndarray, 
                     min2: np.ndarray, max2: np.ndarray) -> bool:
        return np.all(max1 >= min2) and np.all(max2 >= min1)

    def _bounds_similar(self, min1: np.ndarray, max1: np.ndarray, 
                     min2: np.ndarray, max2: np.ndarray, tolerance: float = 0.1) -> bool:
        size1 = max1 - min1
        size2 = max2 - min2
        return np.all(np.abs(size1 - size2) < tolerance)

    def _find_node(self, item_id: str) -> Optional[OctreeNode]:
        """Optimized node finding with early return"""
        def search(node: OctreeNode) -> Optional[OctreeNode]:
            if node.item_id == item_id:
                return node
            if not node.children:  # Early return if no children
                return None
            for child in node.children:
                result = search(child)
                if result:
                    return result
            return None
        return search(self.root)

    def get_item_neighbors(self, item_id: str) -> List[str]:
        """Get items adjacent to the given item using spatial hash for efficiency."""
        if item_id not in self.item_nodes:
            return []
        
        # Use spatial hash for faster neighbor finding
        neighbors = set()
        
        # Get the item's bounds
        node = self.item_nodes[item_id]
        half_size = node.size / 2
        start = node.center - half_size
        end = node.center + half_size
        
        # Calculate grid cells this item occupies
        start_cell = (int(start[0] // self.grid_size), 
                     int(start[1] // self.grid_size), 
                     int(start[2] // self.grid_size))
        end_cell = (int(end[0] // self.grid_size) + 1, 
                   int(end[1] // self.grid_size) + 1, 
                   int(end[2] // self.grid_size) + 1)
        
        # Get all items in those cells and adjacent cells
        for x in range(start_cell[0] - 1, end_cell[0] + 1):
            for y in range(start_cell[1] - 1, end_cell[1] + 1):
                for z in range(start_cell[2] - 1, end_cell[2] + 1):
                    for potential_neighbor in self.spatial_hash.get((x, y, z), []):
                        if potential_neighbor != item_id:
                            neighbors.add(potential_neighbor)
        
        return list(neighbors)

class AdvancedCargoPlacement:
    def __init__(self, container_dims: Dict[str, float]):
        # Initialize with container dimensions
        self.width_cm = container_dims["width_cm"]
        self.depth_cm = container_dims["depth_cm"]
        self.height_cm = container_dims["height_cm"]
        
        # Use sparse matrix instead of full 3D array
        self.space_matrix = SparseMatrix(self.width_cm, self.depth_cm, self.height_cm)
        
        # Pre-load and cache item data
        try:
            # Use Polars for faster CSV loading
            self.items_df = pl.read_csv("imported_items.csv")
            self.items_dict = {str(row["item_id"]): row for row in self.items_df.to_dicts()}
            
            # Create index for faster lookups
            self.dupe_items = {}
            dupe_data = pl.read_csv("dupe_imported_items.csv")
            for row in dupe_data.to_dicts():
                if "item_id" in row:
                    self.dupe_items[str(row["item_id"])] = row
        except Exception as e:
            print(f"Warning: Could not load item data: {str(e)}")
            self.items_df = pl.DataFrame()
            self.items_dict = {}
            self.dupe_items = {}
        
        # Initialize octree with optimized parameters
        center = np.array([self.width_cm/2, self.depth_cm/2, self.height_cm/2])
        size = max(self.width_cm, self.depth_cm, self.height_cm)
        # Reduce max_depth for faster operations
        self.octree = SpaceOctree(center, size, max_depth=4)
        
        # Pre-calculate all possible rotations to avoid redundant calculations
        self.rotation_cache = {}

    def calculate_accessibility_score(self, pos: Position3D, item: ItemDimensions) -> float:
        """Optimized accessibility score calculation"""
        try:
            # Convert item_id to string for consistency
            item_id_str = str(item.item_id)
            
            # 1. Priority Score (40%) - simplify calculation
            priority_score = item.priority / 100
            
            # 2. Expiry Score (25%) - use cached item data
            expiry_score = 1.0
            
            item_data = self.items_dict.get(item_id_str, {})
            if item_data and "expiry_date" in item_data and item_data["expiry_date"]:
                try:
                    expiry = datetime.strptime(str(item_data["expiry_date"]), "%d-%m-%y")
                    current_date = datetime.now()
                    days_until_expiry = (expiry - current_date).days
                    # Simplified calculation
                    expiry_score = max(0.1, min(1.0, 1 - (days_until_expiry / 100)))
                except (ValueError, TypeError):
                    pass
            
            # 3. Usage Score (25%) - use cached item data
            usage_score = 0.5  # Default
            dupe_item = self.dupe_items.get(item_id_str, {})
            if item_data and dupe_item and "usage_limit" in item_data and "usage_limit" in dupe_item:
                try:
                    current_usage_limit = float(item_data["usage_limit"])
                    dupe_usage_limit = float(dupe_item["usage_limit"])
                    if dupe_usage_limit > 0:
                        usage_score = min(1.0, current_usage_limit / dupe_usage_limit)
                except (ValueError, TypeError):
                    pass
            
            # 4. Blockage Score (10%) - simplify calculation
            blockage_score = 0.9  # Default
            
            # Calculate weighted score
            final_score = (
                0.4 * priority_score +
                0.25 * expiry_score +
                0.25 * usage_score +
                0.1 * blockage_score
            )
            
            return round(final_score, 2)
        except Exception as e:
            print(f"Error calculating accessibility score: {str(e)}")
            return 0.5  # Default score to avoid failures

    def _is_blocking(self, neighbor_id: str, target_pos: Position3D) -> bool:
        """Simplified blocking check"""
        neighbor_node = self.octree.item_nodes.get(neighbor_id)
        if not neighbor_node:
            return False
        
        # Simplified check: just compare centers
        neighbor_center = neighbor_node.center
        return (0 <= neighbor_center[0] <= target_pos.x and
                0 <= neighbor_center[1] <= target_pos.y and
                0 <= neighbor_center[2] <= target_pos.z)
    
    def _can_place_item(self, pos: Position3D, item: ItemDimensions) -> bool:
        """Check if an item can be placed at a given position using sparse matrix."""
        # Check boundaries
        if (pos.x + item.width_cm > self.width_cm or
            pos.y + item.depth_cm > self.depth_cm or
            pos.z + item.height_cm > self.height_cm):
            return False

        # Check if space is already occupied using sparse matrix
        return not self.space_matrix.is_occupied(
            pos.x, pos.y, pos.z,
            int(pos.x + item.width_cm),
            int(pos.y + item.depth_cm),
            int(pos.z + item.height_cm)
        )

    def _place_item(self, pos: Position3D, item: ItemDimensions) -> None:
        """Place an item using sparse matrix"""
        self.space_matrix.occupy(
            pos.x, pos.y, pos.z,
            int(pos.x + item.width_cm),
            int(pos.y + item.depth_cm),
            int(pos.z + item.height_cm)
        )

    def get_90degree_rotations(self, item: ItemDimensions) -> List[Tuple[ItemDimensions, Rotation]]:
        """Get rotations with caching for performance"""
        # Use cache if available
        cache_key = (item.width_cm, item.depth_cm, item.height_cm, item.priority)
        if cache_key in self.rotation_cache:
            return self.rotation_cache[cache_key]
        
        # Calculate rotations
        rotations = []
        
        # Original orientation
        rotations.append((
            ItemDimensions(
                width_cm=item.width_cm,
                depth_cm=item.depth_cm,
                height_cm=item.height_cm,
                priority=item.priority,
                mass_kg=item.mass_kg,
                item_id=item.item_id
            ),
            Rotation.NO_ROTATION
        ))
        
        # Rotate around X axis (90°)
        rotations.append((
            ItemDimensions(
                width_cm=item.width_cm,
                depth_cm=item.height_cm,
                height_cm=item.depth_cm,
                priority=item.priority,
                mass_kg=item.mass_kg,
                item_id=item.item_id
            ),
            Rotation.ROTATE_X
        ))
        
        # Rotate around Y axis (90°)
        rotations.append((
            ItemDimensions(
                width_cm=item.height_cm,
                depth_cm=item.depth_cm,
                height_cm=item.width_cm,
                priority=item.priority,
                mass_kg=item.mass_kg,
                item_id=item.item_id
            ),
            Rotation.ROTATE_Y
        ))
        
        # Rotate around Z axis (90°)
        rotations.append((
            ItemDimensions(
                width_cm=item.depth_cm,
                depth_cm=item.width_cm,
                height_cm=item.height_cm,
                priority=item.priority,
                mass_kg=item.mass_kg,
                item_id=item.item_id
            ),
            Rotation.ROTATE_Z
        ))
        
        # Filter valid rotations
        valid_rotations = [
            (rot, name) for rot, name in rotations
            if (rot.width_cm <= self.width_cm and 
                rot.depth_cm <= self.depth_cm and 
                rot.height_cm <= self.height_cm)
        ]
        
        # Cache for future use
        self.rotation_cache[cache_key] = valid_rotations
        
        return valid_rotations

    def find_optimal_placement(self, items: List[Dict]) -> List[Dict]:
        """Optimized placement algorithm with early stopping and intelligent search"""
        placements = []
        
        # Sort items by priority and volume
        sorted_items = sorted(
            items,
            key=lambda x: (x["priority"], x["width_cm"] * x["depth_cm"] * x["height_cm"]),
            reverse=True
        )
        
        # Group similar items for batch processing
        item_groups = {}
        for item in sorted_items:
            key = (item["width_cm"], item["depth_cm"], item["height_cm"], item["priority"])
            if key not in item_groups:
                item_groups[key] = []
            item_groups[key].append(item)
        
        # Build a height map to place items at optimal heights
        height_map = np.zeros((int(self.width_cm), int(self.depth_cm)), dtype=np.int32)
        
        # Process each group of similar items
        for dimensions, group_items in item_groups.items():
            for item_dict in group_items:
                item = ItemDimensions(
                    width_cm=item_dict["width_cm"],
                    depth_cm=item_dict["depth_cm"],
                    height_cm=item_dict["height_cm"],
                    priority=item_dict["priority"],
                    mass_kg=item_dict.get("mass_kg", 0),
                    item_id=item_dict["item_id"]
                )

                # Get valid rotations
                rotations = self.get_90degree_rotations(item)
                
                # Try each rotation
                best_placement = None
                best_score = -1
                best_rotation = None
                
                for rotated_item, rotation in rotations:
                    # Adaptive search strategy
                    # 1. First try to place on existing items (minimize vertical space)
                    if placements:
                        # Sample potential positions from height map
                        candidate_positions = []
                        
                        # Find suitable positions on height map
                        for x in range(0, int(self.width_cm - rotated_item.width_cm + 1), 2):
                            for y in range(0, int(self.depth_cm - rotated_item.depth_cm + 1), 2):
                                # Get the highest point in this region
                                region_height = np.max(height_map[x:x+int(rotated_item.width_cm), 
                                                                y:y+int(rotated_item.depth_cm)])
                                
                                # Try to place at this height
                                if region_height + rotated_item.height_cm <= self.height_cm:
                                    candidate_positions.append(Position3D(x, y, region_height))
                        
                        # Sort positions by height (highest first for efficient packing)
                        candidate_positions.sort(key=lambda pos: pos.z, reverse=True)
                        
                        # Consider only top 20% of positions for detailed evaluation
                        top_positions = candidate_positions[:max(5, len(candidate_positions)//5)]
                        
                        for pos in top_positions:
                            if self._can_place_item(pos, rotated_item):
                                score = self.calculate_accessibility_score(pos, rotated_item)
                                if score > best_score:
                                    best_score = score
                                    best_placement = (pos, rotated_item)
                                    best_rotation = rotation
                    
                    # 2. If no placement found, use a grid search with adaptive steps
                    if best_placement is None:
                        # Adaptive step size based on container dimensions
                        step_size = max(1, min(int(self.width_cm//20), int(self.depth_cm//20)))
                        
                        # Try bottom-up placement to minimize vertical space
                        for z in range(0, int(self.height_cm - rotated_item.height_cm + 1)):
                            found_in_layer = False
                            
                            for x in range(0, int(self.width_cm - rotated_item.width_cm + 1), step_size):
                                for y in range(0, int(self.depth_cm - rotated_item.depth_cm + 1), step_size):
                                    pos = Position3D(x, y, z)
                                    
                                    if self._can_place_item(pos, rotated_item):
                                        score = self.calculate_accessibility_score(pos, rotated_item)
                                        
                                        if score > best_score:
                                            best_score = score
                                            best_placement = (pos, rotated_item)
                                            best_rotation = rotation
                                            found_in_layer = True
                            
                            # Early stopping - if we found a good placement in this layer,
                            # don't check higher layers
                            if found_in_layer and best_score > 0.7:
                                break
                
                # If placement found, place the item
                if best_placement:
                    pos, rotated_item = best_placement
                    self._place_item(pos, rotated_item)
                    
                    # Update height map
                    height_map[pos.x:pos.x+int(rotated_item.width_cm), 
                             pos.y:pos.y+int(rotated_item.depth_cm)] = pos.z + rotated_item.height_cm
                    
                    # Create placement record
                    placement = {
                        "item_id": item_dict["item_id"],
                        "position": {
                            "startCoordinates": {
                                "width_cm": float(pos.x),
                                "depth_cm": float(pos.y),
                                "height_cm": float(pos.z)
                            },
                            "endCoordinates": {
                                "width_cm": float(pos.x + rotated_item.width_cm),
                                "depth_cm": float(pos.y + rotated_item.depth_cm),
                                "height_cm": float(pos.z + rotated_item.height_cm)
                            }
                        },
                        "rotation": best_rotation.value,
                        "accessibilityScore": best_score
                    }
                    
                    # Add to octree
                    self.octree.insert_item(
                        item_dict["item_id"],
                        placement["position"],
                        best_rotation.value,
                        item.priority
                    )
                    
                    placements.append(placement)
        
        return placements