from typing import Dict, List, Union, Optional, Tuple, Any
from dataclasses import dataclass
import re
from collections import defaultdict

@dataclass
class Coordinates:
    width_cm: float
    depth_cm: float
    height_cm: float

@dataclass
class Position:
    startCoordinates: Coordinates
    endCoordinates: Coordinates

class ItemSearchSystem:
    def __init__(self, items_data: List[dict], containers_data: List[dict], cargo_data: List[dict]):
        """Initialize with data from API endpoint"""
        # Process items data
        self.items_data = {}
        for item in items_data:
            item_id = str(item.get("item_id", ""))
            if item_id:
                self.items_data[item_id] = {
                    "name": item.get("name", ""),
                    "width_cm": float(item.get("width_cm", 0)),
                    "depth_cm": float(item.get("depth_cm", 0)),
                    "height_cm": float(item.get("height_cm", 0)),
                    "priority": int(item.get("priority", 1)),
                    "usage_limit": int(item.get("usage_limit", 0))
                }
        
        # Process containers data
        self.containers = {}
        for cont in containers_data:
            container_id = str(cont.get("container_id", ""))
            if container_id:
                self.containers[container_id] = {
                    "container_id": container_id,
                    "zone": cont.get("zone", ""),
                    "width_cm": float(cont.get("width_cm", 0)),
                    "depth_cm": float(cont.get("depth_cm", 0)),
                    "height_cm": float(cont.get("height_cm", 0))
                }

        # Process cargo data with positions
        self.cargo_data = {}
        for item in cargo_data:
            item_id = str(item.get("item_id", ""))
            if not item_id:
                continue
                
            coords_str = item.get("coordinates", "")
            if not coords_str:
                continue
                
            # Extract coordinates using regex
            coords = re.findall(r'[-+]?\d*\.\d+|[-+]?\d+', coords_str)
            if len(coords) >= 6:
                try:
                    self.cargo_data[item_id] = {
                        "zone": item.get("zone", ""),
                        "container_id": item.get("container_id", ""),
                        "position": {
                            "startCoordinates": {
                                "width_cm": float(coords[0]),
                                "depth_cm": float(coords[1]),
                                "height_cm": float(coords[2])
                            },
                            "endCoordinates": {
                                "width_cm": float(coords[3]),
                                "depth_cm": float(coords[4]),
                                "height_cm": float(coords[5])
                            }
                        }
                    }
                except (ValueError, IndexError) as e:
                    print(f"Error processing coordinates for item {item_id}: {e}")

    def search_by_id(self, item_id: Union[int, str]) -> dict:
        """Search for item by ID and calculate optimal retrieval steps"""
        item_id = str(item_id)
        
        if item_id not in self.items_data:
            return {
                "success": True,
                "found": False,
                "message": f"Item {item_id} not found in inventory"
            }
            
        if item_id not in self.cargo_data:
            return {
                "success": True,
                "found": False,
                "message": f"Item {item_id} exists but not placed in any container"
            }

        item_data = self.items_data[item_id]
        cargo_info = self.cargo_data[item_id]
        zone = cargo_info["zone"]
        
        # Find container for zone
        container_id = next(
            (cid for cid, cont in self.containers.items() if cont["zone"] == zone),
            None
        )
        
        if not container_id:
            return {
                "success": False,
                "found": False,
                "message": f"No container found for zone {zone}"
            }

        # Calculate retrieval steps
        retrieval_steps = self._calculate_retrieval_steps(item_id, zone)

        return {
            "success": True,
            "found": True,
            "item": {
                "item_id": int(item_id),
                "name": item_data["name"],
                "container_id": container_id,
                "zone": zone,
                "position": cargo_info["position"]
            },
            "retrieval_steps": retrieval_steps
        }

    def search_by_name(self, item_name: str) -> dict:
        """Search for item by name"""
        for item_id, data in self.items_data.items():
            if data["name"].lower() == item_name.lower():
                return self.search_by_id(item_id)
                
        return {
            "success": True,
            "found": False,
            "message": f"Item with name '{item_name}' not found"
        }

    def _calculate_retrieval_steps(self, target_item_id: str, zone: str) -> List[dict]:
        """Calculate optimal retrieval steps for an item using a dependency graph approach"""
        target_item_id = str(target_item_id)
        target_item = self.cargo_data[target_item_id]
        target_container = target_item["container_id"]
        target_start = target_item["position"]["startCoordinates"]
        target_end = target_item["position"]["endCoordinates"]
        target_priority = self.items_data[target_item_id]["priority"]
        
        # Find all items in the same container
        items_in_container = {
            str(item_id): data for item_id, data in self.cargo_data.items()
            if data["container_id"] == target_container and str(item_id) != target_item_id
        }
        
        # Build dependency graph
        blocking_items = []
        
        for item_id, item_data in items_in_container.items():
            item_start = item_data["position"]["startCoordinates"]
            item_end = item_data["position"]["endCoordinates"]
            item_priority = self.items_data[item_id]["priority"]
            
            # Check if item is in front of target (blocking)
            is_blocking = (
                # Item is in front of target (starts at a lower depth)
                item_start["depth_cm"] < target_start["depth_cm"] and
                # Width overlap (items are side by side)
                not (item_end["width_cm"] <= target_start["width_cm"] or 
                     item_start["width_cm"] >= target_end["width_cm"]) and
                # Priority check
                item_priority > target_priority
            )
            
            if is_blocking:
                blocking_items.append({
                    "item_id": item_id,
                    "name": self.items_data[item_id]["name"],
                    "position": item_data["position"],
                    "priority": item_priority
                })
        
        # If no blocking items, return empty list (0 steps needed)
        if not blocking_items:
            return []
        
        # Sort blocking items by depth (front to back)
        blocking_items.sort(key=lambda x: x["position"]["startCoordinates"]["depth_cm"])
        
        # Generate retrieval steps
        steps = []
        step_number = 1
        
        # Remove blocking items (front to back)
        for item in blocking_items:
            steps.append({
                "step": step_number,
                "action": "remove",
                "item_id": int(item["item_id"]),
                "item_name": item["name"]
            })
            step_number += 1
        
        # Retrieve target item
        steps.append({
            "step": step_number,
            "action": "retrieve",
            "item_id": int(target_item_id),
            "item_name": self.items_data[target_item_id]["name"]
        })
        step_number += 1
        
        # Place back blocking items (back to front)
        for item in reversed(blocking_items):
            steps.append({
                "step": step_number,
                "action": "place",
                "item_id": int(item["item_id"]),
                "item_name": item["name"]
            })
            step_number += 1
        
        return steps