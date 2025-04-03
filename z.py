from typing import Dict, List, Set, Optional
from dataclasses import dataclass
from collections import defaultdict

@dataclass
class Position3D:
    x: float
    y: float
    z: float

@dataclass
class ItemInfo:
    item_id: int
    width_cm: float
    depth_cm: float
    height_cm: float
    position: Position3D

class StorageOptimizer:
    def __init__(self, container_dims: Dict[str, float]):
        self.width_cm = container_dims["width_cm"]
        self.depth_cm = container_dims["depth_cm"]
        self.height_cm = container_dims["height_cm"]
        self.items = []
        self.spatial_index = defaultdict(set)

    def add_items(self, items: List[ItemInfo]) -> None:
        """Add items and build spatial index"""
        self.items = items
        self._build_spatial_index()

    def _build_spatial_index(self) -> None:
        """Build spatial index for efficient item location"""
        self.spatial_index.clear()
        for item in self.items:
            self.spatial_index[item.position.y].add(item)

    def retrieve_item(self, target_id: int) -> List[Dict]:
        """Generate retrieval steps for target item"""
        # Find target item
        target = next((item for item in self.items if item.item_id == target_id), None)
        if not target:
            return [{"error": f"Item {target_id} not found"}]

        # Find blocking items
        blocking_items = self._find_blocking_items(target)
        if not blocking_items:
            return [{
                "action": "retrieve",
                "item_id": target_id,
                "position": {
                    "width_cm": target.position.x,
                    "depth_cm": target.position.y,
                    "height_cm": target.position.z
                }
            }]

        # Generate retrieval steps
        steps = []
        moved_items = []

        # Move blocking items
        for blocking_item in blocking_items:
            temp_pos = self._find_temp_position(blocking_item)
            steps.append({
                "action": "move",
                "item_id": blocking_item.item_id,
                "from": {
                    "width_cm": blocking_item.position.x,
                    "depth_cm": blocking_item.position.y,
                    "height_cm": blocking_item.position.z
                },
                "to": {
                    "width_cm": temp_pos.x,
                    "depth_cm": temp_pos.y,
                    "height_cm": temp_pos.z
                }
            })
            moved_items.append((blocking_item, blocking_item.position))
            blocking_item.position = temp_pos

        # Retrieve target
        steps.append({
            "action": "retrieve",
            "item_id": target_id,
            "position": {
                "width_cm": target.position.x,
                "depth_cm": target.position.y,
                "height_cm": target.position.z
            }
        })

        # Return blocking items
        for item, orig_pos in reversed(moved_items):
            steps.append({
                "action": "restore",
                "item_id": item.item_id,
                "from": {
                    "width_cm": item.position.x,
                    "depth_cm": item.position.y,
                    "height_cm": item.position.z
                },
                "to": {
                    "width_cm": orig_pos.x,
                    "depth_cm": orig_pos.y,
                    "height_cm": orig_pos.z
                }
            })
            item.position = orig_pos

        return steps

    def _find_blocking_items(self, target: ItemInfo) -> List[ItemInfo]:
        """Find all items blocking access to target"""
        blocking_items = []
        target_footprint = (
            (target.position.x, target.position.x + target.width_cm),
            (target.position.z, target.position.z + target.height_cm)
        )

        # Check all layers in front of target
        for depth in sorted(self.spatial_index.keys()):
            if depth >= target.position.y:
                break

            # Check items in this layer
            for item in self.spatial_index[depth]:
                if self._is_blocking(item, target_footprint):
                    blocking_items.append(item)

        return blocking_items

    def _is_blocking(self, item: ItemInfo, target_footprint: tuple) -> bool:
        """Check if item blocks access to target footprint"""
        item_footprint = (
            (item.position.x, item.position.x + item.width_cm),
            (item.position.z, item.position.z + item.height_cm)
        )
        
        # Check overlap in width and height
        x_overlap = max(item_footprint[0][0], target_footprint[0][0]) < min(item_footprint[0][1], target_footprint[0][1])
        z_overlap = max(item_footprint[1][0], target_footprint[1][0]) < min(item_footprint[1][1], target_footprint[1][1])
        
        return x_overlap and z_overlap

    def _find_temp_position(self, item: ItemInfo) -> Position3D:
        """Find temporary position for item"""
        return Position3D(x=0, y=0, z=self.height_cm - item.height_cm)