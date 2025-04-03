from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Tuple, Union, Set
import numpy as np
from datetime import datetime
import polars as pl
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
    """Optimized sparse 3D matrix implementation"""
    def __init__(self, width_cm, depth_cm, height_cm):
        self.width_cm = int(width_cm)
        self.depth_cm = int(depth_cm)
        self.height_cm = int(height_cm)
        # Use a set of tuples for faster lookup
        self.occupied_cells = set()
        # Add a 2D height map for faster placement
        self.height_map = np.zeros((int(width_cm), int(depth_cm)), dtype=np.int32)

    def is_occupied(self, x_start, y_start, z_start, x_end, y_end, z_end):
        """OPTIMIZED: Check region occupancy using bounding box test instead of cell iteration"""
        # First quick check: is anything in this region by height?
        region_max_height = np.max(self.height_map[x_start:x_end, y_start:y_end])
        if region_max_height <= z_start:
            return False
            
        # Check if any occupied cell is in our region
        for occupied_x, occupied_y, occupied_z in self.occupied_cells:
            if (x_start <= occupied_x < x_end and 
                y_start <= occupied_y < y_end and 
                z_start <= occupied_z < z_end):
                return True
        return False

    def occupy(self, x_start, y_start, z_start, x_end, y_end, z_end):
        """OPTIMIZED: Mark corners + center instead of all cells"""
        # Only store the corners and center of the occupied region
        corners = [
            (x_start, y_start, z_start),
            (x_end-1, y_start, z_start),
            (x_start, y_end-1, z_start),
            (x_end-1, y_end-1, z_start),
            (x_start, y_start, z_end-1),
            (x_end-1, y_start, z_end-1),
            (x_start, y_end-1, z_end-1),
            (x_end-1, y_end-1, z_end-1),
            # Center point
            ((x_start + x_end) // 2, (y_start + y_end) // 2, (z_start + z_end) // 2)
        ]
        self.occupied_cells.update(corners)
        
        # Update height map
        self.height_map[x_start:x_end, y_start:y_end] = np.maximum(
            self.height_map[x_start:x_end, y_start:y_end],
            z_end
        )

class DependencyGraph:
    """Graph to track dependencies between placed items"""
    def __init__(self):
        self.dependencies = defaultdict(set)
        self.dependents = defaultdict(set)
        self.item_positions = {}

    def add_item(self, item_id: str, position: Dict):
        self.item_positions[item_id] = position

    def add_dependency(self, item_id: str, dependency_id: str):
        self.dependencies[item_id].add(dependency_id)
        self.dependents[dependency_id].add(item_id)

    def get_dependencies(self, item_id: str) -> Set[str]:
        return self.dependencies.get(item_id, set())

    def get_dependents(self, item_id: str) -> Set[str]:
        return self.dependents.get(item_id, set())

    def get_all_items(self) -> Set[str]:
        all_items = set(self.dependencies.keys()) | set(self.dependents.keys())
        return all_items

    def is_dependent(self, item1: str, item2: str) -> bool:
        # OPTIMIZED: Use BFS instead of DFS for better performance in this case
        queue = [item1]
        visited = {item1}
        
        while queue:
            current = queue.pop(0)
            if current == item2:
                return True
                
            for dep in self.dependencies.get(current, set()):
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)
        return False

    def get_removal_order(self) -> List[str]:
        """Get a valid order to remove items (no dependencies violated)"""
        result = []
        in_degree = {item: len(self.dependencies[item]) for item in self.get_all_items()}
        queue = [item for item, degree in in_degree.items() if degree == 0]
        
        while queue:
            current = queue.pop(0)
            result.append(current)
            
            for dependent in list(self.dependents.get(current, set())):
                self.dependencies[dependent].remove(current)
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
                    
        return result

class SpatialHashGrid:
    """OPTIMIZED: Faster spatial hash grid for neighbor finding"""
    def __init__(self, width, depth, height, cell_size):
        self.cell_size = cell_size
        self.grid = defaultdict(list)
        
    def add_item(self, item_id, start, end):
        """Add item to all cells it intersects"""
        start_cell = tuple(int(coord // self.cell_size) for coord in start)
        end_cell = tuple(int(coord // self.cell_size) + 1 for coord in end)
        
        # Only store cell references instead of full 3D iteration
        for x in range(start_cell[0], end_cell[0]):
            for y in range(start_cell[1], end_cell[1]):
                for z in range(start_cell[2], end_cell[2]):
                    self.grid[(x, y, z)].append(item_id)
    
    def get_items_in_region(self, start, end):
        """Get all items in a region"""
        start_cell = tuple(int(coord // self.cell_size) for coord in start)
        end_cell = tuple(int(coord // self.cell_size) + 1 for coord in end)
        
        items = set()
        for x in range(start_cell[0], end_cell[0]):
            for y in range(start_cell[1], end_cell[1]):
                for z in range(start_cell[2], end_cell[2]):
                    items.update(self.grid.get((x, y, z), []))
        
        return items

class AdvancedCargoPlacement:
    def __init__(self, container_dims: Dict[str, float]):
        # Initialize with container dimensions
        self.width_cm = container_dims["width_cm"]
        self.depth_cm = container_dims["depth_cm"]
        self.height_cm = container_dims["height_cm"]
        
        # Use optimized sparse matrix
        self.space_matrix = SparseMatrix(self.width_cm, self.depth_cm, self.height_cm)
        
        # OPTIMIZATION: Precompute and cache frequently accessed data
        self.expiry_scores = {}
        self.usage_scores = {}
        
        # Pre-load and cache item data
        try:
            # OPTIMIZATION: Use Polars with specific schema and column selection
            schema = {
                "item_id": pl.Utf8,
                "expiry_date": pl.Utf8,
                "usage_limit": pl.Float64
            }
            self.items_df = pl.read_csv("imported_items.csv", schema=schema)
            self.items_dict = {str(row["item_id"]): row for row in self.items_df.to_dicts()}
            
            # OPTIMIZATION: Create a faster lookup for duplicate items
            self.dupe_items = {}
            dupe_schema = {"item_id": pl.Utf8, "usage_limit": pl.Float64}
            dupe_data = pl.read_csv("dupe_imported_items.csv", schema=dupe_schema)
            for row in dupe_data.to_dicts():
                if "item_id" in row:
                    self.dupe_items[str(row["item_id"])] = row
                    
            # OPTIMIZATION: Precompute scores for all items
            self._precompute_scores()
        except Exception as e:
            print(f"Warning: Could not load item data: {str(e)}")
            self.items_df = pl.DataFrame()
            self.items_dict = {}
            self.dupe_items = {}
        
        # OPTIMIZATION: Use a more efficient spatial data structure
        self.spatial_hash = SpatialHashGrid(
            self.width_cm, self.depth_cm, self.height_cm, 
            cell_size=max(10, min(self.width_cm, self.depth_cm, self.height_cm) / 20)
        )
        
        # OPTIMIZATION: Pre-calculate all possible rotations
        self.rotation_cache = {}
        
        # Initialize dependency graph
        self.dependency_graph = DependencyGraph()
        
        # OPTIMIZATION: Use fixed grid positions for placement candidates
        self.grid_positions = self._precompute_grid_positions()

    def _precompute_grid_positions(self):
        """Precompute a set of grid positions to try for placement"""
        positions = []
        
        # Use a coarser grid for faster search
        step_size = max(5, min(int(self.width_cm//10), int(self.depth_cm//10)))
        
        for x in range(0, int(self.width_cm), step_size):
            for y in range(0, int(self.depth_cm), step_size):
                # Start at z=0, heights will be determined dynamically
                positions.append((x, y))
        
        return positions
        
    def _precompute_scores(self):
        """OPTIMIZATION: Precompute expiry and usage scores for all items"""
        current_date = datetime.now()
        
        for item_id, item_data in self.items_dict.items():
            # Compute expiry score
            if "expiry_date" in item_data and item_data["expiry_date"]:
                try:
                    expiry = datetime.strptime(str(item_data["expiry_date"]), "%d-%m-%y")
                    days_until_expiry = (expiry - current_date).days
                    expiry_score = max(0.1, min(1.0, 1 - (days_until_expiry / 100)))
                    self.expiry_scores[item_id] = expiry_score
                except (ValueError, TypeError):
                    self.expiry_scores[item_id] = 1.0
            else:
                self.expiry_scores[item_id] = 1.0
                
            # Compute usage score
            dupe_item = self.dupe_items.get(item_id, {})
            if "usage_limit" in item_data and "usage_limit" in dupe_item:
                try:
                    current_usage_limit = float(item_data["usage_limit"])
                    dupe_usage_limit = float(dupe_item["usage_limit"])
                    if dupe_usage_limit > 0:
                        usage_score = min(1.0, current_usage_limit / dupe_usage_limit)
                        self.usage_scores[item_id] = usage_score
                    else:
                        self.usage_scores[item_id] = 0.5
                except (ValueError, TypeError):
                    self.usage_scores[item_id] = 0.5
            else:
                self.usage_scores[item_id] = 0.5

    def calculate_accessibility_score(self, pos: Position3D, item: ItemDimensions) -> float:
        """OPTIMIZED: Much faster accessibility score calculation using cached values"""
        # Convert item_id to string for consistency
        item_id_str = str(item.item_id)
        
        # 1. Priority Score (40%) - direct calculation
        priority_score = item.priority / 100
        
        # 2. Expiry Score (25%) - use cached score
        expiry_score = self.expiry_scores.get(item_id_str, 1.0)
        
        # 3. Usage Score (25%) - use cached score
        usage_score = self.usage_scores.get(item_id_str, 0.5)
        
        # 4. Blockage Score (10%) - simplified calculation
        blockage_score = 0.9
        
        # Calculate weighted score
        final_score = (
            0.4 * priority_score +
            0.25 * expiry_score +
            0.25 * usage_score +
            0.1 * blockage_score
        )
        
        return round(final_score, 2)

    def _can_place_item(self, pos: Position3D, item: ItemDimensions) -> bool:
        """OPTIMIZED: Check if an item can be placed at a given position"""
        # Check boundaries first (fast rejection)
        if (pos.x + item.width_cm > self.width_cm or
            pos.y + item.depth_cm > self.depth_cm or
            pos.z + item.height_cm > self.height_cm):
            return False

        # Check if space is already occupied using optimized sparse matrix
        return not self.space_matrix.is_occupied(
            pos.x, pos.y, pos.z,
            int(pos.x + item.width_cm),
            int(pos.y + item.depth_cm),
            int(pos.z + item.height_cm)
        )

    def _place_item(self, pos: Position3D, item: ItemDimensions, item_id: str, rotation: Rotation) -> Dict:
        """OPTIMIZED: Place an item and create placement record"""
        self.space_matrix.occupy(
            pos.x, pos.y, pos.z,
            int(pos.x + item.width_cm),
            int(pos.y + item.depth_cm),
            int(pos.z + item.height_cm)
        )
        
        # Create placement record
        placement = {
            "item_id": item_id,
            "position": {
                "startCoordinates": {
                    "width_cm": float(pos.x),
                    "depth_cm": float(pos.y),
                    "height_cm": float(pos.z)
                },
                "endCoordinates": {
                    "width_cm": float(pos.x + item.width_cm),
                    "depth_cm": float(pos.y + item.depth_cm),
                    "height_cm": float(pos.z + item.height_cm)
                }
            },
            "rotation": rotation.value,
            "accessibilityScore": self.calculate_accessibility_score(pos, item)
        }
        
        # Add to spatial hash
        self.spatial_hash.add_item(
            str(item_id),
            [pos.x, pos.y, pos.z],
            [pos.x + item.width_cm, pos.y + item.depth_cm, pos.z + item.height_cm]
        )
        
        # Add to dependency graph
        item_id_str = str(item_id)
        self.dependency_graph.add_item(item_id_str, placement["position"])
        
        # Identify supporting items
        self._add_support_dependencies(item_id_str, placement["position"])
        
        return placement

    def _add_support_dependencies(self, item_id: str, position: Dict) -> None:
        """OPTIMIZED: Add support dependencies more efficiently"""
        # Extract coordinates
        start_x = position["startCoordinates"]["width_cm"]
        start_y = position["startCoordinates"]["depth_cm"]
        start_z = position["startCoordinates"]["height_cm"]
        end_x = position["endCoordinates"]["width_cm"]
        end_y = position["endCoordinates"]["depth_cm"]
        
        # Skip if item is on the floor
        if start_z == 0:
            return
            
        # Look for items directly below this item (check only a few points)
        below_start = [start_x, start_y, start_z - 1]
        below_end = [end_x, end_y, start_z]
        
        potential_supports = self.spatial_hash.get_items_in_region(below_start, below_end)
        
        # Add dependencies
        for support_id in potential_supports:
            if support_id != item_id:
                self.dependency_graph.add_dependency(item_id, support_id)

    def get_rotations(self, item: ItemDimensions) -> List[Tuple[ItemDimensions, Rotation]]:
        """OPTIMIZED: Get rotations with more efficient caching"""
        # Use cache if available
        cache_key = (item.width_cm, item.depth_cm, item.height_cm)
        if cache_key in self.rotation_cache:
            # Create copies with the correct item_id and priority
            cached_rotations = self.rotation_cache[cache_key]
            return [
                (
                    ItemDimensions(
                        width_cm=r.width_cm,
                        depth_cm=r.depth_cm,
                        height_cm=r.height_cm,
                        priority=item.priority,
                        mass_kg=item.mass_kg,
                        item_id=item.item_id
                    ),
                    rot
                )
                for r, rot in cached_rotations
            ]
        
        # Calculate rotations (only unique ones, avoiding duplicates)
        rotations = []
        
        # Create base item for caching (without id and priority)
        base_item = ItemDimensions(
            width_cm=item.width_cm,
            depth_cm=item.depth_cm,
            height_cm=item.height_cm,
            priority=0,  # We'll replace this later
            mass_kg=item.mass_kg
        )
        
        # Original orientation
        rotations.append((base_item, Rotation.NO_ROTATION))
        
        # Add unique rotations only
        dimensions_seen = {(item.width_cm, item.depth_cm, item.height_cm)}
        
        # Check X rotation
        x_dims = (item.width_cm, item.height_cm, item.depth_cm)
        if x_dims not in dimensions_seen:
            dimensions_seen.add(x_dims)
            rotations.append((
                ItemDimensions(
                    width_cm=item.width_cm,
                    depth_cm=item.height_cm,
                    height_cm=item.depth_cm,
                    priority=0,
                    mass_kg=item.mass_kg
                ),
                Rotation.ROTATE_X
            ))
        
        # Check Y rotation
        y_dims = (item.height_cm, item.depth_cm, item.width_cm)
        if y_dims not in dimensions_seen:
            dimensions_seen.add(y_dims)
            rotations.append((
                ItemDimensions(
                    width_cm=item.height_cm,
                    depth_cm=item.depth_cm,
                    height_cm=item.width_cm,
                    priority=0,
                    mass_kg=item.mass_kg
                ),
                Rotation.ROTATE_Y
            ))
        
        # Check Z rotation
        z_dims = (item.depth_cm, item.width_cm, item.height_cm)
        if z_dims not in dimensions_seen:
            dimensions_seen.add(z_dims)
            rotations.append((
                ItemDimensions(
                    width_cm=item.depth_cm,
                    depth_cm=item.width_cm,
                    height_cm=item.height_cm,
                    priority=0,
                    mass_kg=item.mass_kg
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
        
        # Return copies with the correct item_id and priority
        return [
            (
                ItemDimensions(
                    width_cm=r.width_cm,
                    depth_cm=r.depth_cm,
                    height_cm=r.height_cm,
                    priority=item.priority,
                    mass_kg=r.mass_kg,
                    item_id=item.item_id
                ),
                rot
            )
            for r, rot in valid_rotations
        ]

    def find_optimal_placement(self, items: List[Dict]) -> List[Dict]:
        """OPTIMIZED: Much faster placement algorithm"""
        placements = []
        
        # OPTIMIZATION: Group similar items by dimensions for batch processing
        dimension_groups = defaultdict(list)
        for item in items:
            key = (item["width_cm"], item["depth_cm"], item["height_cm"])
            dimension_groups[key].append(item)
        
        # Sort groups by priority and volume (largest and highest priority first)
        sorted_groups = sorted(
            dimension_groups.items(),
            key=lambda x: (
                max(item["priority"] for item in x[1]),  # Max priority in group
                x[0][0] * x[0][1] * x[0][2]  # Volume
            ),
            reverse=True
        )
        
        # Process each group
        for _, group_items in sorted_groups:
            # Sort items in group by priority
            group_items.sort(key=lambda x: x["priority"], reverse=True)
            
            for item_dict in group_items:
                item = ItemDimensions(
                    width_cm=item_dict["width_cm"],
                    depth_cm=item_dict["depth_cm"],
                    height_cm=item_dict["height_cm"],
                    priority=item_dict["priority"],
                    mass_kg=item_dict.get("mass_kg", 0),
                    item_id=item_dict["item_id"]
                )

                # Get valid rotations (only unique)
                rotations = self.get_rotations(item)
                
                # Try each rotation
                best_placement = None
                best_score = -1
                best_rotation = None
                best_item = None
                
                for rotated_item, rotation in rotations:
                    # OPTIMIZATION: Prioritize positions based on height map
                    # Try precomputed grid positions but dynamically get Z from height map
                    for x, y in self.grid_positions:
                        # Skip if out of bounds
                        if (x + rotated_item.width_cm > self.width_cm or 
                            y + rotated_item.depth_cm > self.depth_cm):
                            continue
                        
                        # Get height for this position from height map
                        region_slice = self.space_matrix.height_map[
                            x:min(x+int(rotated_item.width_cm), self.width_cm),
                            y:min(y+int(rotated_item.depth_cm), self.depth_cm)
                        ]
                        
                        if region_slice.size > 0:
                            z = np.max(region_slice)
                            
                            # Skip if out of bounds
                            if z + rotated_item.height_cm > self.height_cm:
                                continue
                                
                            pos = Position3D(x, y, z)
                            
                            # Fast check if we can place here
                            if self._can_place_item(pos, rotated_item):
                                # Calculate score only for valid positions
                                score = self.calculate_accessibility_score(pos, rotated_item)
                                
                                # Update best if better
                                if score > best_score:
                                    best_score = score
                                    best_placement = pos
                                    best_rotation = rotation
                                    best_item = rotated_item
                                    
                                    # Early stopping - if score is good enough
                                    if score > 0.8:
                                        break
                    
                    # Early stopping if we found a good placement
                    if best_score > 0.8:
                        break
                
                # If placement found, place the item
                if best_placement and best_item and best_rotation:
                    placement = self._place_item(
                        best_placement, 
                        best_item,
                        item_dict["item_id"],
                        best_rotation
                    )
                    placements.append(placement)
        
        return placements