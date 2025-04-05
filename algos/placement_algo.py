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

# Add CSV caching at the module level
_CSV_CACHE = {}

def load_csv(filename):
    """Optimized CSV loading with caching"""
    if filename not in _CSV_CACHE:
        try:
            _CSV_CACHE[filename] = pl.read_csv(filename).to_dicts()
        except Exception as e:
            print(f"Error loading CSV {filename}: {str(e)}")
            _CSV_CACHE[filename] = {}
    return _CSV_CACHE[filename]

class SparseMatrix:
    """Optimized Sparse 3D matrix implementation using spatial partitioning"""
    def __init__(self, width_cm, depth_cm, height_cm, grid_size=10):
        self.width_cm = int(width_cm)
        self.depth_cm = int(depth_cm)
        self.height_cm = int(height_cm)
        self.grid_size = grid_size
        # Use a dictionary of sets for better performance
        self.grid = defaultdict(set)
        self.occupied_cells = set()
        # Track item positions
        self.item_positions = {}

    def _get_grid_cell(self, x, y, z):
        return (x // self.grid_size, y // self.grid_size, z // self.grid_size)

    def is_occupied(self, x_start, y_start, z_start, x_end, y_end, z_end):
        """Optimized occupancy check using grid-based spatial partitioning"""
        # Get grid cells that this region spans
        start_cell = self._get_grid_cell(x_start, y_start, z_start)
        end_cell = self._get_grid_cell(x_end, y_end, z_end)
        
        # Check only the relevant grid cells
        for x in range(start_cell[0], end_cell[0] + 1):
            for y in range(start_cell[1], end_cell[1] + 1):
                for z in range(start_cell[2], end_cell[2] + 1):
                    if (x, y, z) in self.grid and self.grid[(x, y, z)]:
                        return True
        return False

    def occupy(self, x_start, y_start, z_start, x_end, y_end, z_end):
        """Optimized occupation marking using grid-based spatial partitioning"""
        start_cell = self._get_grid_cell(x_start, y_start, z_start)
        end_cell = self._get_grid_cell(x_end, y_end, z_end)
        
        for x in range(start_cell[0], end_cell[0] + 1):
            for y in range(start_cell[1], end_cell[1] + 1):
                for z in range(start_cell[2], end_cell[2] + 1):
                    self.grid[(x, y, z)].add((x_start, y_start, z_start, x_end, y_end, z_end))
                    self.occupied_cells.add((x, y, z))

    def clear(self, x_start, y_start, z_start, x_end, y_end, z_end):
        """Clear a region from the grid"""
        start_cell = self._get_grid_cell(x_start, y_start, z_start)
        end_cell = self._get_grid_cell(x_end, y_end, z_end)
        
        for x in range(start_cell[0], end_cell[0] + 1):
            for y in range(start_cell[1], end_cell[1] + 1):
                for z in range(start_cell[2], end_cell[2] + 1):
                    if (x, y, z) in self.grid:
                        self.grid[(x, y, z)].discard((x_start, y_start, z_start, x_end, y_end, z_end))
                        if not self.grid[(x, y, z)]:
                            self.occupied_cells.discard((x, y, z))

    def get_occupied_regions(self):
        """Get all occupied regions in the grid"""
        regions = set()
        for cell in self.occupied_cells:
            regions.update(self.grid[cell])
        return regions

class SpaceOctree:
    def __init__(self, center: np.ndarray, size: float, max_depth: int = 4):
        self.root = OctreeNode(center, size, [])
        self.max_depth = max_depth
        self.item_nodes = {}
        self.spatial_hash = defaultdict(list)
        self.grid_size = size / 8
        # Add cache for bounds checks
        self._bounds_cache = {}

    def _get_cached_bounds(self, start: np.ndarray, end: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Cache bounds calculations for better performance"""
        key = (tuple(start), tuple(end))
        if key not in self._bounds_cache:
            self._bounds_cache[key] = (start, end)
        return self._bounds_cache[key]

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
        
        # Use cached bounds
        start, end = self._get_cached_bounds(start, end)
        
        # Try to find a suitable node without recursion first
        node = self._find_suitable_node(start, end)
        if node:
            node.occupied = True
            node.item_id = item_id_str
            node.rotation = rotation
            node.priority = priority
            self.item_nodes[item_id_str] = node
            self._add_to_spatial_hash(item_id_str, start, end)
            return True
            
        # If no suitable node found, try recursive insertion
        success = self._insert_recursive(self.root, start, end, item_id_str, rotation, priority)
        if success:
            node = self._find_node(item_id_str)
            self.item_nodes[item_id_str] = node
            self._add_to_spatial_hash(item_id_str, start, end)
        return success

    def _find_suitable_node(self, start: np.ndarray, end: np.ndarray) -> Optional[OctreeNode]:
        """Non-recursive node finding with early termination"""
        queue = [self.root]
        while queue:
            node = queue.pop(0)
            if node.occupied:
                continue
                
            node_min = node.center - node.size/2
            node_max = node.center + node.size/2
            
            if not self._bounds_overlap(start, end, node_min, node_max):
                continue
                
            if self._bounds_similar(start, end, node_min, node_max):
                return node
                
            if node.children:
                queue.extend(node.children)
            elif node.depth < self.max_depth:
                self.subdivide(node)
                queue.extend(node.children)
                
        return None

    def _insert_recursive(self, node: OctreeNode, start: np.ndarray, end: np.ndarray, 
                         item_id: str, rotation: str, priority: int) -> bool:
        if node.occupied:
            return False

        node_min = node.center - node.size/2
        node_max = node.center + node.size/2

        if not self._bounds_overlap(start, end, node_min, node_max):
            return False

        if self._bounds_similar(start, end, node_min, node_max):
            node.occupied = True
            node.item_id = item_id
            node.rotation = rotation
            node.priority = priority
            return True

        if not node.children and node.depth < self.max_depth:
            self.subdivide(node)

        if node.children:
            for child in node.children:
                if self._insert_recursive(child, start, end, item_id, rotation, priority):
                    return True

        return False

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
    # Class-level storage for container states
    _container_states = {}

    def __init__(self, container_dims: Dict[str, float]):
        # Convert dimensions to integers
        self.width_cm = int(container_dims["width_cm"])
        self.depth_cm = int(container_dims["depth_cm"])
        self.height_cm = int(container_dims["height_cm"])
        
        # Create a unique key for this container
        self.container_key = f"{self.width_cm}x{self.depth_cm}x{self.height_cm}"
        
        # Initialize or retrieve existing state
        if self.container_key not in self._container_states:
            self._container_states[self.container_key] = {
                'space_matrix': SparseMatrix(self.width_cm, self.depth_cm, self.height_cm),
                'current_placements': {},
                'rearrangement_history': []
            }
        
        # Use the shared state
        self.space_matrix = self._container_states[self.container_key]['space_matrix']
        self.current_placements = self._container_states[self.container_key]['current_placements']
        self.rearrangement_history = self._container_states[self.container_key]['rearrangement_history']
        
        # Initialize without CSV loading
        self.items_dict = {}
        self._item_cache = {}
        self._dupe_cache = {}
        self.rotation_cache = {}

    def _get_cached_item(self, item_id: str) -> Optional[Dict]:
        """Get cached item data with memoization"""
        if item_id not in self._item_cache:
            if item_id in self.items_dict:
                self._item_cache[item_id] = self.items_dict[item_id]
            elif item_id in self._dupe_cache:
                self._item_cache[item_id] = self._dupe_cache[item_id]
            else:
                return None
        return self._item_cache[item_id]

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
            dupe_item = self._dupe_cache.get(item_id_str, {})
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
        # Convert item dimensions to integers
        item_width = int(item.width_cm)
        item_depth = int(item.depth_cm)
        item_height = int(item.height_cm)
        
        # Check boundaries
        if (pos.x + item_width > self.width_cm or
            pos.y + item_depth > self.depth_cm or
            pos.z + item_height > self.height_cm):
            return False

        # Check if space is already occupied using sparse matrix
        return not self.space_matrix.is_occupied(
            pos.x, pos.y, pos.z,
            pos.x + item_width,
            pos.y + item_depth,
            pos.z + item_height
        )

    def _place_item(self, pos: Position3D, item: ItemDimensions) -> None:
        """Place an item using sparse matrix"""
        # Convert item dimensions to integers
        item_width = int(item.width_cm)
        item_depth = int(item.depth_cm)
        item_height = int(item.height_cm)
        
        self.space_matrix.occupy(
            pos.x, pos.y, pos.z,
            pos.x + item_width,
            pos.y + item_depth,
            pos.z + item_height
        )

    def get_90degree_rotations(self, item: ItemDimensions) -> List[Tuple[ItemDimensions, Rotation]]:
        """Get all valid 90-degree rotations for an item"""
        rotations = []
        
        # Original orientation
        rotations.append((item, Rotation.NO_ROTATION))
        
        # Rotate around X axis (90°)
        if item.height_cm <= self.depth_cm and item.depth_cm <= self.height_cm:
            rotated = ItemDimensions(
                width_cm=item.width_cm,
                depth_cm=item.height_cm,
                height_cm=item.depth_cm,
                priority=item.priority,
                mass_kg=item.mass_kg,
                item_id=item.item_id
            )
            rotations.append((rotated, Rotation.ROTATE_X))
        
        # Rotate around Y axis (90°)
        if item.width_cm <= self.height_cm and item.height_cm <= self.width_cm:
            rotated = ItemDimensions(
                width_cm=item.height_cm,
                depth_cm=item.depth_cm,
                height_cm=item.width_cm,
                priority=item.priority,
                mass_kg=item.mass_kg,
                item_id=item.item_id
            )
            rotations.append((rotated, Rotation.ROTATE_Y))
        
        # Rotate around Z axis (90°)
        if item.width_cm <= self.depth_cm and item.depth_cm <= self.width_cm:
            rotated = ItemDimensions(
                width_cm=item.depth_cm,
                depth_cm=item.width_cm,
                height_cm=item.height_cm,
                priority=item.priority,
                mass_kg=item.mass_kg,
                item_id=item.item_id
            )
            rotations.append((rotated, Rotation.ROTATE_Z))
        
        return rotations

    def _calculate_rearrangement_cost(self, old_pos: Position3D, new_pos: Position3D, item: ItemDimensions) -> float:
        """Calculate the cost of moving an item from old position to new position"""
        # Distance cost (Euclidean distance)
        distance = np.sqrt(
            (new_pos.x - old_pos.x)**2 +
            (new_pos.y - old_pos.y)**2 +
            (new_pos.z - old_pos.z)**2
        )
        
        # Priority cost (higher priority items are more expensive to move)
        priority_cost = item.priority / 100.0
        
        # Mass cost (heavier items are more expensive to move)
        mass_cost = item.mass_kg / 100.0
        
        # Total cost is weighted combination
        return distance * (1 + priority_cost + mass_cost)

    def _find_rearrangement_path(self, item: ItemDimensions, target_pos: Position3D) -> List[Dict]:
        """Find the optimal path to rearrange items to make space for a new item"""
        # Get current position of the item
        current_pos = self.current_placements.get(str(item.item_id))
        if not current_pos:
            return []

        # Calculate potential moves
        moves = []
        temp_positions = []
        
        # Try to find a temporary position for the item
        temp_pos = self._find_temporary_position(item)
        if temp_pos:
            moves.append({
                'item_id': str(item.item_id),
                'from': {
                    'x': current_pos.x,
                    'y': current_pos.y,
                    'z': current_pos.z
                },
                'to': {
                    'x': temp_pos.x,
                    'y': temp_pos.y,
                    'z': temp_pos.z
                },
                'type': 'temporary'
            })
            temp_positions.append(temp_pos)
        
        # Move to final position
        moves.append({
            'item_id': str(item.item_id),
            'from': {
                'x': temp_pos.x if temp_pos else current_pos.x,
                'y': temp_pos.y if temp_pos else current_pos.y,
                'z': temp_pos.z if temp_pos else current_pos.z
            },
            'to': {
                'x': target_pos.x,
                'y': target_pos.y,
                'z': target_pos.z
            },
            'type': 'final'
        })
        
        return moves

    def _find_temporary_position(self, item: ItemDimensions) -> Optional[Position3D]:
        """Find a temporary position for an item during rearrangement"""
        # Try to find a position that doesn't require moving other items
        for x in range(0, self.width_cm - int(item.width_cm) + 1, 10):
            for y in range(0, self.depth_cm - int(item.depth_cm) + 1, 10):
                for z in range(0, self.height_cm - int(item.height_cm) + 1, 10):
                    pos = Position3D(x, y, z)
                    if self._can_place_item(pos, item):
                        return pos
        return None

    def rearrange_for_new_item(self, new_item: ItemDimensions) -> Tuple[List[Dict], bool]:
        """Attempt to rearrange existing items to make space for a new item"""
        rearrangements = []
        success = False
        
        # Get existing items with their priorities
        existing_items = []
        for item_id, pos in self.current_placements.items():
            # Get the item's dimensions and priority from the original data
            item_data = self.items_dict.get(item_id, {})
            if item_data:
                existing_items.append({
                    'item_id': item_id,
                    'position': pos,
                    'priority': item_data.get('priority', 0),
                    'mass_kg': item_data.get('mass_kg', 0),
                    'width_cm': item_data.get('width_cm', 0),
                    'depth_cm': item_data.get('depth_cm', 0),
                    'height_cm': item_data.get('height_cm', 0)
                })
        
        # Sort existing items by priority and mass (move less important items first)
        existing_items.sort(key=lambda x: (x['priority'], x['mass_kg']))
        
        # Try to find a position for the new item
        target_pos = self._find_best_position(new_item)
        if not target_pos:
            # If no direct position found, try rearranging
            for existing_item in existing_items:
                # Create ItemDimensions for the existing item
                item_dim = ItemDimensions(
                    width_cm=existing_item['width_cm'],
                    depth_cm=existing_item['depth_cm'],
                    height_cm=existing_item['height_cm'],
                    priority=existing_item['priority'],
                    mass_kg=existing_item['mass_kg'],
                    item_id=existing_item['item_id']
                )
                
                # Calculate potential moves
                moves = self._find_rearrangement_path(item_dim, target_pos)
                if moves:
                    rearrangements.extend(moves)
                    # Update current placements
                    for move in moves:
                        if move['type'] == 'final':
                            self.current_placements[move['item_id']] = Position3D(
                                move['to']['x'],
                                move['to']['y'],
                                move['to']['z']
                            )
                    success = True
                    break
        
        return rearrangements, success

    def find_optimal_placement(self, items: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Optimized placement algorithm with rearrangement support"""
        if not items:
            return [], []

        # Store all items in items_dict for later reference
        for item in items:
            item_id = str(item.get('item_id'))
            self.items_dict[item_id] = {
                'width_cm': item.get('width_cm', 0),
                'depth_cm': item.get('depth_cm', 0),
                'height_cm': item.get('height_cm', 0),
                'priority': item.get('priority', 0),
                'mass_kg': item.get('mass_kg', 0),
                'item_id': item_id
            }

        # Sort items by priority and size for better placement
        sorted_items = sorted(items, 
                           key=lambda x: (-x.get('priority', 0), 
                                        -(x.get('width_cm', 0) * 
                                          x.get('depth_cm', 0) * 
                                          x.get('height_cm', 0))))
        
        placements = []
        rearrangements = []
        
        # First, try to place all items without rearrangement
        for item in sorted_items:
            item_id = str(item.get('item_id'))
            # Create ItemDimensions from input data
            item_dim = ItemDimensions(
                width_cm=item.get('width_cm', 0),
                depth_cm=item.get('depth_cm', 0),
                height_cm=item.get('height_cm', 0),
                priority=item.get('priority', 0),
                mass_kg=item.get('mass_kg', 0),
                item_id=item_id
            )
            
            # Try different rotations
            rotations = self.get_90degree_rotations(item_dim)
            placed = False
            
            for rotated_item, rotation in rotations:
                # Find best position for this rotation
                best_pos = self._find_best_position(rotated_item)
                if best_pos and self._can_place_item(best_pos, rotated_item):
                    # Place the item
                    self._place_item(best_pos, rotated_item)
                    self.current_placements[item_id] = best_pos
                    
                    placements.append({
                        'item_id': item_id,
                        'position': {
                            'startCoordinates': {
                                'width_cm': float(best_pos.x),
                                'depth_cm': float(best_pos.y),
                                'height_cm': float(best_pos.z)
                            },
                            'endCoordinates': {
                                'width_cm': float(best_pos.x + rotated_item.width_cm),
                                'depth_cm': float(best_pos.y + rotated_item.depth_cm),
                                'height_cm': float(best_pos.z + rotated_item.height_cm)
                            }
                        },
                        'rotation': rotation.value
                    })
                    placed = True
                    break
        
        # Now try to place any remaining items with rearrangement
        for item in sorted_items:
            item_id = str(item.get('item_id'))
            if item_id in [p['item_id'] for p in placements]:
                continue
                
            item_dim = ItemDimensions(
                width_cm=item.get('width_cm', 0),
                depth_cm=item.get('depth_cm', 0),
                height_cm=item.get('height_cm', 0),
                priority=item.get('priority', 0),
                mass_kg=item.get('mass_kg', 0),
                item_id=item_id
            )
            
            # Try different rotations
            rotations = self.get_90degree_rotations(item_dim)
            placed = False
            
            for rotated_item, rotation in rotations:
                # Find best position for this rotation
                best_pos = self._find_best_position(rotated_item)
                if best_pos:
                    # Check if rearrangement is needed
                    if not self._can_place_item(best_pos, rotated_item):
                        # Try to rearrange existing items
                        item_rearrangements, success = self.rearrange_for_new_item(rotated_item)
                        if success:
                            rearrangements.extend(item_rearrangements)
                            # Update the space matrix after rearrangement
                            for move in item_rearrangements:
                                if move['type'] == 'final':
                                    # Clear old position
                                    old_pos = Position3D(
                                        move['from']['x'],
                                        move['from']['y'],
                                        move['from']['z']
                                    )
                                    self.space_matrix.clear(
                                        old_pos.x, old_pos.y, old_pos.z,
                                        old_pos.x + int(rotated_item.width_cm),
                                        old_pos.y + int(rotated_item.depth_cm),
                                        old_pos.z + int(rotated_item.height_cm)
                                    )
                                    # Mark new position
                                    new_pos = Position3D(
                                        move['to']['x'],
                                        move['to']['y'],
                                        move['to']['z']
                                    )
                                    self.space_matrix.occupy(
                                        new_pos.x, new_pos.y, new_pos.z,
                                        new_pos.x + int(rotated_item.width_cm),
                                        new_pos.y + int(rotated_item.depth_cm),
                                        new_pos.z + int(rotated_item.height_cm)
                                    )
                    
                    # Place the item
                    self._place_item(best_pos, rotated_item)
                    self.current_placements[item_id] = best_pos
                    
                    placements.append({
                        'item_id': item_id,
                        'position': {
                            'startCoordinates': {
                                'width_cm': float(best_pos.x),
                                'depth_cm': float(best_pos.y),
                                'height_cm': float(best_pos.z)
                            },
                            'endCoordinates': {
                                'width_cm': float(best_pos.x + rotated_item.width_cm),
                                'depth_cm': float(best_pos.y + rotated_item.depth_cm),
                                'height_cm': float(best_pos.z + rotated_item.height_cm)
                            }
                        },
                        'rotation': rotation.value
                    })
                    placed = True
                    break
                
        return placements, rearrangements

    def _find_best_position(self, item: ItemDimensions) -> Optional[Position3D]:
        """Optimized position finding with spatial partitioning"""
        # Use grid-based search
        grid_size = 10
        # Convert item dimensions to integers
        item_width = int(item.width_cm)
        item_depth = int(item.depth_cm)
        item_height = int(item.height_cm)
        
        # First try to find a position that doesn't require rearrangement
        for x in range(0, self.width_cm - item_width + 1, grid_size):
            for y in range(0, self.depth_cm - item_depth + 1, grid_size):
                for z in range(0, self.height_cm - item_height + 1, grid_size):
                    pos = Position3D(x, y, z)
                    if self._can_place_item(pos, item):
                        return pos
        
        # If no direct position found, try to find a position that requires minimal rearrangement
        best_pos = None
        min_rearrangement_cost = float('inf')
        
        for x in range(0, self.width_cm - item_width + 1, grid_size):
            for y in range(0, self.depth_cm - item_depth + 1, grid_size):
                for z in range(0, self.height_cm - item_height + 1, grid_size):
                    pos = Position3D(x, y, z)
                    # Check if this position overlaps with any existing items
                    if self.space_matrix.is_occupied(x, y, z, x + item_width, y + item_depth, z + item_height):
                        # Calculate rearrangement cost for this position
                        cost = self._calculate_rearrangement_cost_for_position(pos, item)
                        if cost < min_rearrangement_cost:
                            min_rearrangement_cost = cost
                            best_pos = pos
        
        return best_pos

    def _calculate_rearrangement_cost_for_position(self, pos: Position3D, item: ItemDimensions) -> float:
        """Calculate the cost of rearranging items to make space for a new item at the given position"""
        total_cost = 0.0
        item_width = int(item.width_cm)
        item_depth = int(item.depth_cm)
        item_height = int(item.height_cm)
        
        # Get all occupied regions that overlap with the target position
        for region in self.space_matrix.get_occupied_regions():
            x_start, y_start, z_start, x_end, y_end, z_end = region
            if (pos.x < x_end and pos.x + item_width > x_start and
                pos.y < y_end and pos.y + item_depth > y_start and
                pos.z < z_end and pos.z + item_height > z_start):
                # Calculate cost to move this item
                old_pos = Position3D(x_start, y_start, z_start)
                # Find a temporary position
                temp_pos = self._find_temporary_position(item)
                if temp_pos:
                    cost = self._calculate_rearrangement_cost(old_pos, temp_pos, item)
                    total_cost += cost
        
        return total_cost