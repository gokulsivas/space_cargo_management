import heapq
import logging
import time
from collections import defaultdict, deque
import itertools

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SparseMatrix:
    """
    A simple sparse matrix implementation using a dictionary for storing non-zero elements.
    Used here to represent the occupied space on the container floor (X-Z plane).
    """
    def __init__(self):
        self._data = {} # (row, col): value

    def __setitem__(self, key, value):
        # key is expected to be a tuple (row, col)
        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError("Key must be a tuple of (row, col)")
        if value != 0: # Store only non-zero values (occupied cells)
            self._data[key] = value
        elif key in self._data:
            del self._data[key] # Remove zero values if they exist

    def __getitem__(self, key):
        # key is expected to be a tuple (row, col)
        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError("Key must be a tuple of (row, col)")
        return self._data.get(key, 0) # Return 0 for empty cells

    def __delitem__(self, key):
        if key in self._data:
            del self._data[key]

    def get_occupied_cells(self):
        """Returns a list of occupied (row, col) tuples."""
        return list(self._data.keys())

    def is_occupied(self, row, col):
        """Checks if a specific cell is occupied."""
        return (row, col) in self._data

class SpatialHashGrid:
    """
    A spatial hash grid for quickly querying items within a certain 3D region.
    Helps optimize collision detection during placement.
    """
    def __init__(self, cell_size):
        self.cell_size = cell_size
        self.grid = defaultdict(list) # Maps cell coordinates (ix, iy, iz) to list of item_ids in that cell

    def _get_cell_coords(self, x, y, z):
        """Calculates the grid cell coordinates for a given point."""
        return (
            int(x // self.cell_size),
            int(y // self.cell_size),
            int(z // self.cell_size)
        )

    def insert(self, item, x, y, z):
        """Inserts an item into the grid based on its bounding box."""
        item_id = item['item_id']
        min_coords = self._get_cell_coords(x, y, z)
        # Use actual dimensions for max coords calculation
        max_coords = self._get_cell_coords(
            x + item['width'] - 1e-9, # Subtract small epsilon to handle boundary cases
            y + item['depth'] - 1e-9,
            z + item['height'] - 1e-9
        )

        # Add item_id to all cells its bounding box overlaps
        for ix in range(min_coords[0], max_coords[0] + 1):
            for iy in range(min_coords[1], max_coords[1] + 1):
                for iz in range(min_coords[2], max_coords[2] + 1):
                    cell_key = (ix, iy, iz)
                    if item_id not in self.grid[cell_key]:
                         self.grid[cell_key].append(item_id)

    def query(self, x, y, z, width, depth, height):
        """Queries the grid to find potential overlapping items in a given region."""
        min_coords = self._get_cell_coords(x, y, z)
        max_coords = self._get_cell_coords(
            x + width - 1e-9,
            y + depth - 1e-9,
            z + height - 1e-9
        )

        potential_overlaps = set()
        for ix in range(min_coords[0], max_coords[0] + 1):
            for iy in range(min_coords[1], max_coords[1] + 1):
                for iz in range(min_coords[2], max_coords[2] + 1):
                    cell_key = (ix, iy, iz)
                    if cell_key in self.grid:
                        potential_overlaps.update(self.grid[cell_key])
        return list(potential_overlaps)

    def remove(self, item, x, y, z):
        """Removes an item from the grid."""
        item_id = item['item_id']
        min_coords = self._get_cell_coords(x, y, z)
        max_coords = self._get_cell_coords(
             x + item['width'] - 1e-9,
             y + item['depth'] - 1e-9,
             z + item['height'] - 1e-9
        )

        for ix in range(min_coords[0], max_coords[0] + 1):
            for iy in range(min_coords[1], max_coords[1] + 1):
                for iz in range(min_coords[2], max_coords[2] + 1):
                    cell_key = (ix, iy, iz)
                    if cell_key in self.grid and item_id in self.grid[cell_key]:
                        self.grid[cell_key].remove(item_id)
                        if not self.grid[cell_key]: # Clean up empty cell lists
                            del self.grid[cell_key]


class DependencyGraph:
    """
    Represents dependencies between items in the container.
    Includes both support dependencies (what's below an item)
    and blocking dependencies (what's in front of an item).
    """
    def __init__(self):
        # Support dependencies: item -> set of items it rests upon
        self.support_depends_on = defaultdict(set)
        # Support dependencies: item -> set of items resting upon it
        self.supports = defaultdict(set)

        # Blocking dependencies: item -> set of items directly in front of it (blocking it)
        self.blocking_depends_on = defaultdict(set) # Renamed from 'blocking' for clarity
        # Blocking dependencies: item -> set of items it blocks (is in front of)
        self.blocks = defaultdict(set) # Renamed from 'blockers' for clarity

    def add_support_dependency(self, supported_item_id, supporting_item_id):
        """Records that supported_item rests on supporting_item."""
        if supported_item_id != supporting_item_id:
            self.support_depends_on[supported_item_id].add(supporting_item_id)
            self.supports[supporting_item_id].add(supported_item_id)
            # logging.debug(f"Support Dep: {supported_item_id} rests on {supporting_item_id}")

    def add_blocking_dependency(self, blocking_item_id, blocked_item_id):
        """Records that blocking_item is directly in front of blocked_item."""
        if blocking_item_id != blocked_item_id:
            self.blocking_depends_on[blocked_item_id].add(blocking_item_id)
            self.blocks[blocking_item_id].add(blocked_item_id)
            logging.debug(f"Blocking Dep: {blocking_item_id} blocks {blocked_item_id}")

    def get_support_dependencies(self, item_id):
        """Returns the set of items that item_id rests upon."""
        return self.support_depends_on.get(item_id, set())

    def get_items_supported_by(self, item_id):
        """Returns the set of items resting upon item_id."""
        return self.supports.get(item_id, set())

    def get_blocking_items(self, item_id):
        """Returns the set of items directly in front of item_id."""
        return self.blocking_depends_on.get(item_id, set())

    def get_items_blocked_by(self, item_id):
         """Returns the set of items that item_id is directly in front of."""
         return self.blocks.get(item_id, set())

    def get_all_blockers(self, target_item_id):
        """
        Finds all items that directly or indirectly block the target_item_id
        by being in front of it or in front of an item that blocks it, etc.
        Returns a set including the target_item_id itself and all its blockers.
        """
        if target_item_id not in self.blocking_depends_on and target_item_id not in self.blocks:
             # Target item might not be part of any blocking relationship if it's at the very front
             # or if the graph hasn't been fully populated yet. Return just the item itself.
             # Or if it was never placed.
             logging.warning(f"Target item {target_item_id} not found in blocking dependency graph.")
             # Check if it exists in support graph to confirm it was placed
             if target_item_id not in self.support_depends_on and target_item_id not in self.supports:
                 logging.error(f"Target item {target_item_id} not found in any graph. Was it placed?")
                 return set() # Item doesn't seem to exist in the container
             return {target_item_id} # Item exists but has no recorded blockers

        all_blockers = set()
        queue = deque([target_item_id])
        visited = {target_item_id} # Keep track of visited nodes to prevent cycles

        while queue:
            current_item = queue.popleft()
            all_blockers.add(current_item)

            # Find items that directly block the current item
            direct_blockers = self.get_blocking_items(current_item)
            for blocker in direct_blockers:
                if blocker not in visited:
                    visited.add(blocker)
                    queue.append(blocker)

        logging.debug(f"All blockers for {target_item_id}: {all_blockers}")
        return all_blockers

    def get_blocker_removal_order(self, target_item_id):
        """
        Determines the removal order for items blocking the target_item_id.
        Only considers the items identified by get_all_blockers.
        Returns a list of item IDs in the order they should be removed.
        """
        relevant_items = self.get_all_blockers(target_item_id)
        if not relevant_items or target_item_id not in relevant_items:
            # Handle cases where the target wasn't found or has no blockers
             if target_item_id in self.support_depends_on or target_item_id in self.supports:
                 logging.info(f"Item {target_item_id} has no blockers.")
                 return [] # No blockers to remove
             else:
                 logging.error(f"Cannot determine removal order for non-existent item {target_item_id}.")
                 return None # Indicate error

        # --- Topological Sort on the subset of relevant_items ---
        # 1. Calculate in-degrees *within the relevant set*
        in_degree = {item_id: 0 for item_id in relevant_items}
        # Adjacency list *within the relevant set* (blocker -> list of items it blocks)
        adj = {item_id: [] for item_id in relevant_items}

        for blocker_id in relevant_items:
            # Consider items that this blocker blocks
            blocked_items = self.get_items_blocked_by(blocker_id)
            for blocked_id in blocked_items:
                # Only consider edges where BOTH nodes are in the relevant set
                if blocked_id in relevant_items:
                    adj[blocker_id].append(blocked_id)
                    in_degree[blocked_id] += 1

        # 2. Initialize queue with items having in-degree 0 (within the relevant set)
        # These are the items closest to the front among the blockers/target
        queue = deque([item_id for item_id in relevant_items if in_degree[item_id] == 0])
        removal_order = []

        # 3. Process the queue
        while queue:
            # Dequeue an item with in-degree 0
            blocker_to_remove = queue.popleft()
            # Add it to the removal order, *unless* it's the target item itself
            if blocker_to_remove != target_item_id:
                 removal_order.append(blocker_to_remove)

            # 'Remove' its edges: decrease in-degree of its neighbors (within relevant set)
            for blocked_neighbor in adj[blocker_to_remove]:
                # Check again if neighbor is relevant (should always be true based on adj construction)
                if blocked_neighbor in relevant_items:
                    in_degree[blocked_neighbor] -= 1
                    # If neighbor's in-degree becomes 0, add it to the queue
                    if in_degree[blocked_neighbor] == 0:
                        queue.append(blocked_neighbor)

        # 4. Check for cycles (if removal_order length is less than expected)
        # We expect len(removal_order) == len(relevant_items) - 1 (excluding the target)
        if len(removal_order) != len(relevant_items) - 1:
            # This indicates a cycle within the blocking dependencies among the relevant items,
            # or an issue with graph construction/traversal.
            logging.error(f"Cycle detected or error in topological sort for blockers of {target_item_id}.")
            logging.error(f"Relevant items: {relevant_items}")
            logging.error(f"Calculated removal order: {removal_order}")
            # Depending on desired behavior, could return partial order or raise error
            return None # Indicate error

        logging.info(f"Removal order for blockers of {target_item_id}: {removal_order}")
        return removal_order

    def get_removal_order_all(self):
        """
        Performs a topological sort on the *support* graph
        to get a possible order for removing *all* items.
        Items with no support dependencies are removed first.
        """
        # Calculate in-degrees based on support dependencies
        in_degree = defaultdict(int)
        adj = defaultdict(list)
        all_items = set(self.support_depends_on.keys()) | set(self.supports.keys())

        for supported, supporters in self.support_depends_on.items():
            for supporter in supporters:
                adj[supporter].append(supported) # Edge from supporter to supported
                in_degree[supported] += 1

        # Initialize queue with items having in-degree 0 (items not supported by others)
        queue = deque([item for item in all_items if in_degree[item] == 0])
        removal_order = []

        while queue:
            item = queue.popleft()
            removal_order.append(item)

            # For each item that the removed item supports
            for neighbor in adj[item]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check if topological sort included all items (cycle detection)
        if len(removal_order) != len(all_items):
            logging.error("Cycle detected in support dependency graph! Cannot determine full removal order.")
            return None # Or raise an error

        return removal_order


class AdvancedCargoPlacement:
    """
    Advanced algorithm for placing items into containers, considering stability,
    stacking constraints, and using optimization techniques.
    Builds a dependency graph for support and blocking relationships.
    """
    def __init__(self, container_dims):
        """
        Initializes the placement algorithm.

        Args:
            container_dims (dict): {'width': W, 'depth': D, 'height': H}
        """
        self.container_width = container_dims['width']
        self.container_depth = container_dims['depth']
        self.container_height = container_dims['height']

        # Use SparseMatrix for floor plan (X-Z) - might be less useful if stacking complex
        # self.floor_plan = SparseMatrix() # Represents base level (y=0)

        # Use SpatialHashGrid for 3D collision detection
        # Adjust cell size based on typical item dimensions for efficiency
        avg_dim = (self.container_width * self.container_depth * self.container_height)**(1/3)
        cell_size = max(1, int(avg_dim / 10)) # Heuristic for cell size
        self.spatial_grid = SpatialHashGrid(cell_size=cell_size)

        # Store placed items with their positions and dimensions
        # item_id -> {'item': item_details, 'pos': (x, y, z)}
        self.placed_items = {}

        # Dependency graph to track support and blocking
        self.dependency_graph = DependencyGraph()

        # Priority queue for potential placement positions (heuristic based)
        # Stores tuples: (priority_score, x, y, z)
        # Lower score is better. Score could be based on y, then x, then z (fill back-to-front, bottom-up)
        self.position_queue = [(0, 0, 0, 0)] # Start with (score, x, y, z) at origin

        # Keep track of visited/invalidated positions to avoid redundant checks
        self.visited_positions = set([(0,0,0)])


    def _is_valid_position(self, x, y, z, item_dims):
        """Checks if placing an item at (x, y, z) is valid."""
        width, depth, height = item_dims['width'], item_dims['depth'], item_dims['height']

        # 1. Boundary Check: Ensure item fits within container dimensions
        if not (0 <= x and x + width <= self.container_width and
                0 <= y and y + depth <= self.container_depth and
                0 <= z and z + height <= self.container_height):
            # logging.debug(f"Boundary check failed for pos ({x},{y},{z}) dims ({width},{depth},{height})")
            return False

        # 2. Collision Check: Use spatial grid to find potential overlaps
        potential_collisions = self.spatial_grid.query(x, y, z, width, depth, height)
        for other_item_id in potential_collisions:
            if other_item_id in self.placed_items:
                other_item_info = self.placed_items[other_item_id]
                ox, oy, oz = other_item_info['pos']
                ow, od, oh = other_item_info['item']['width'], other_item_info['item']['depth'], other_item_info['item']['height']

                # Precise AABB collision check
                if (x < ox + ow and x + width > ox and
                    y < oy + od and y + depth > oy and
                    z < oz + oh and z + height > oz):
                    # logging.debug(f"Collision detected with item {other_item_id} at ({ox},{oy},{oz})")
                    return False # Collision detected

        # 3. Stability Check (Simplified): Ensure item rests on something solid below
        # Check if the base of the item has sufficient support
        if z > 0: # Only need support if not on the container floor
            support_found = False
            # Check immediately below the item's footprint
            support_query_z = z - 1e-6 # Check just below
            min_support_z = max(0, z - 1) # Check within a small range below

            # Query slightly below the item's base area
            items_below = self.spatial_grid.query(x, y, min_support_z, width, depth, z - min_support_z)

            for below_item_id in items_below:
                 if below_item_id in self.placed_items:
                    below_info = self.placed_items[below_item_id]
                    bx, by, bz = below_info['pos']
                    bw, bd, bh = below_info['item']['width'], below_info['item']['depth'], below_info['item']['height']

                    # Check if the top surface of the item below is exactly at z
                    # And if the item below provides overlap in X-Y plane
                    if abs((bz + bh) - z) < 1e-6: # Check if top surface aligns with base of new item
                         # Check for sufficient overlap (simplistic: any overlap is okay)
                         overlap_x = max(0, min(x + width, bx + bw) - max(x, bx))
                         overlap_y = max(0, min(y + depth, by + bd) - max(y, by))
                         if overlap_x > 0 and overlap_y > 0:
                             support_found = True
                             break # Found sufficient support from at least one item

            if not support_found:
                 # logging.debug(f"Stability check failed at z={z}: No support found below.")
                 return False

        return True # Position is valid


    def _add_support_dependencies(self, placed_item, x, y, z):
        """Find items directly below and add support dependencies."""
        item_id = placed_item['item_id']
        width, depth = placed_item['width'], placed_item['depth']

        if z == 0: # Item is on the floor, no support dependencies
            return

        # Query region directly below the item
        query_z = z - 1e-6 # Look just below the item's base
        min_z_check = max(0, z - 1) # Check a small slice below

        items_below = self.spatial_grid.query(x, y, min_z_check, width, depth, z - min_z_check)

        for below_item_id in items_below:
            if below_item_id == item_id or below_item_id not in self.placed_items:
                continue

            below_info = self.placed_items[below_item_id]
            bx, by, bz = below_info['pos']
            bw, bd, bh = below_info['item']['width'], below_info['item']['depth'], below_info['item']['height']

            # Check if the top surface of the item below is exactly at z
            if abs((bz + bh) - z) < 1e-6:
                 # Check for overlap in X-Y plane
                 overlap_x = max(0, min(x + width, bx + bw) - max(x, bx))
                 overlap_y = max(0, min(y + depth, by + bd) - max(y, by))
                 if overlap_x > 0 and overlap_y > 0:
                     # Add dependency: placed_item rests on below_item_id
                     self.dependency_graph.add_support_dependency(item_id, below_item_id)


    def _update_blocking_dependencies(self, placed_item, x, y, z):
        """
        Checks for items directly in front or behind the newly placed item
        and updates the blocking dependencies in the graph.
        Assumes Y is the depth axis (smaller Y is closer to the front).
        """
        placed_item_id = placed_item['item_id']
        pw, pd, ph = placed_item['width'], placed_item['depth'], placed_item['height']

        # Define the X-Z footprint of the placed item
        placed_x_range = (x, x + pw)
        placed_z_range = (z, z + ph)

        # Iterate through already placed items to check for blocking
        # Using spatial grid query can optimize this if needed, but iterating
        # might be acceptable if the number of items isn't enormous.
        # Query a large region along the Y-axis covering the X-Z footprint
        items_to_check = self.spatial_grid.query(x, 0, z, pw, self.container_depth, ph)

        # for existing_item_id, existing_info in self.placed_items.items():
        for existing_item_id in items_to_check:
             if existing_item_id == placed_item_id or existing_item_id not in self.placed_items:
                 continue

             existing_info = self.placed_items[existing_item_id]
             existing_item = existing_info['item']
             ex, ey, ez = existing_info['pos']
             ew, ed, eh = existing_item['width'], existing_item['depth'], existing_item['height']

             # Check for overlap in X and Z dimensions
             x_overlap = (placed_x_range[0] < ex + ew) and (placed_x_range[1] > ex)
             z_overlap = (placed_z_range[0] < ez + eh) and (placed_z_range[1] > ez)

             if x_overlap and z_overlap:
                 # Items overlap in X-Z plane, now check Y (depth)
                 placed_y_end = y + pd
                 existing_y_end = ey + ed

                 # Check if existing item is BEHIND the placed item
                 if ey >= placed_y_end: # Existing starts at or after placed ends
                      # Check if there's no gap between them along Y
                      if abs(ey - placed_y_end) < 1e-6:
                           # Placed item is directly in front of existing item
                           self.dependency_graph.add_blocking_dependency(
                               blocking_item_id=placed_item_id,
                               blocked_item_id=existing_item_id
                           )

                 # Check if existing item is IN FRONT of the placed item
                 elif y >= existing_y_end: # Placed starts at or after existing ends
                      # Check if there's no gap between them along Y
                      if abs(y - existing_y_end) < 1e-6:
                           # Existing item is directly in front of placed item
                           self.dependency_graph.add_blocking_dependency(
                               blocking_item_id=existing_item_id,
                               blocked_item_id=placed_item_id
                           )
                 # Else: They overlap in Y dimension (collision - should not happen if placement is correct)
                 # Or there is a gap between them along Y axis.


    def _get_next_potential_positions(self, last_placed_item, x, y, z):
        """Generates potential next positions based on the last placement."""
        # Simple strategy: Try placing next to the item just placed
        # (right, front, top)
        w, d, h = last_placed_item['width'], last_placed_item['depth'], last_placed_item['height']
        potential = [
            (x + w, y, z), # Right
            (x, y + d, z), # Front (further back)
            (x, y, z + h)  # Top
        ]
        # Add corners relative to the container origin as well
        # (0,0,0) is already handled by initialization
        # Add corners relative to the placed item might be better
        corners = [
            (x + w, y + d, z),
            (x + w, y, z + h),
            (x, y + d, z + h),
            (x + w, y + d, z + h),
        ]
        potential.extend(corners)

        new_positions = []
        for px, py, pz in potential:
            # Basic validity check (within bounds) - more checks in _is_valid_position
            if (0 <= px < self.container_width and
                0 <= py < self.container_depth and
                0 <= pz < self.container_height and
                (px, py, pz) not in self.visited_positions):
                 # Calculate priority score (e.g., prefer lower Y, then lower Z, then lower X)
                 score = py * 1e6 + pz * 1e3 + px # Heuristic score
                 new_positions.append((score, px, py, pz))
                 self.visited_positions.add((px,py,pz))

        return new_positions


    def _place_item(self, item):
        """Finds the best valid position and places the item."""
        item_dims = {'width': item['width'], 'depth': item['depth'], 'height': item['height']}
        item_id = item['item_id']

        # Use the priority queue to explore promising positions first
        checked_positions_count = 0
        max_checks = 10000 # Limit checks to prevent infinite loops in tricky scenarios

        temp_rejected_positions = [] # Store positions rejected for this item but maybe ok for others

        while self.position_queue and checked_positions_count < max_checks:
            try:
                priority, x, y, z = heapq.heappop(self.position_queue)
            except IndexError:
                logging.warning("Position queue is empty.")
                break # No more positions to check

            checked_positions_count += 1

            # Check if position is valid for the current item
            if self._is_valid_position(x, y, z, item_dims):
                logging.info(f"Placing item {item_id} at ({x}, {y}, {z})")

                # Place the item
                self.placed_items[item_id] = {'item': item, 'pos': (x, y, z)}
                self.spatial_grid.insert(item, x, y, z)

                # Update dependencies
                self._add_support_dependencies(item, x, y, z)
                self._update_blocking_dependencies(item, x, y, z)

                # Generate and add next potential positions to the queue
                next_positions = self._get_next_potential_positions(item, x, y, z)
                for score, nx, ny, nz in next_positions:
                     heapq.heappush(self.position_queue, (score, nx, ny, nz))

                # Add back the temporarily rejected positions for future items
                for pos in temp_rejected_positions:
                    heapq.heappush(self.position_queue, pos)

                return True # Item placed successfully

            else:
                 # Position (x,y,z) is not valid for *this* item,
                 # but might be valid for a smaller item later.
                 # Keep it in consideration but don't add it back immediately
                 # to avoid infinite loops if it's fundamentally blocked.
                 # A better approach might be needed here.
                 # For now, just discard it for this item and continue.
                 # Add it to a temporary list
                 temp_rejected_positions.append((priority, x, y, z))


        # If loop finishes without placing, add rejected positions back
        for pos in temp_rejected_positions:
            heapq.heappush(self.position_queue, pos)

        logging.warning(f"Could not find a valid position for item {item_id} after {checked_positions_count} checks.")
        return False


    def place_items(self, items):
        """
        Places a list of items into the container.

        Args:
            items (list): List of item dictionaries, each with
                          'item_id', 'width', 'depth', 'height',
                          and potentially 'priority' or 'constraints'.

        Returns:
            tuple: (dict_of_placed_items, dependency_graph_instance)
                   dict_of_placed_items: {item_id: {'item': item, 'pos': (x, y, z)}}
                   Returns None for placed_items if placement fails for any item.
        """
        start_time = time.time()

        # Sort items (optional, e.g., by size, priority)
        # Sorting by volume descending can sometimes be effective (heuristic)
        items.sort(key=lambda i: i['width'] * i['depth'] * i['height'], reverse=True)

        placed_count = 0
        for item in items:
            if self._place_item(item):
                placed_count += 1
            else:
                logging.error(f"Placement failed for item {item['item_id']}. Aborting.")
                # Decide on behavior: return partial placement or None
                # Returning None indicates full placement wasn't possible
                # return None, self.dependency_graph # Return graph even on failure?
                break # Stop placement if one item fails


        end_time = time.time()
        logging.info(f"Placement attempt finished in {end_time - start_time:.4f} seconds.")
        logging.info(f"Successfully placed {placed_count} out of {len(items)} items.")

        # Return the final placements and the generated dependency graph
        # Only return placements if all items were placed (or adjust as needed)
        if placed_count == len(items):
             return self.placed_items, self.dependency_graph
        else:
             # Return partial placement and graph for debugging/analysis
             logging.warning("Returning partial placement results.")
             return self.placed_items, self.dependency_graph


# Example Usage (can be removed or kept for testing)
