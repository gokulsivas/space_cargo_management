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
        self.items_data = {
            str(item["item_id"]): {
                "name": item["name"],
                "width_cm": float(item["width_cm"]),
                "depth_cm": float(item["depth_cm"]),
                "height_cm": float(item["height_cm"]),
                "priority": int(item.get("priority", 1)),
                "usage_limit": int(item.get("usage_limit", 0))
            }
            for item in items_data
        }
        
        self.containers = {
            str(cont["container_id"]): {
                "container_id": str(cont["container_id"]),
                "zone": cont["zone"],
                "width_cm": float(cont["width_cm"]),
                "depth_cm": float(cont["depth_cm"]),
                "height_cm": float(cont["height_cm"])
            }
            for cont in containers_data
        }

        # Process cargo data with positions
        self.cargo_data = {}
        for item in cargo_data:
            item_id = str(item["item_id"])
            coords = re.findall(r'[-+]?\d*\.\d+|[-+]?\d+', item["coordinates"])
            if len(coords) >= 6:
                self.cargo_data[item_id] = {
                    "zone": item["zone"],
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

    def search_by_id(self, item_id: Union[int, str]) -> dict:
        """Search for item by ID"""
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
            "retrieval_steps": self._generate_retrieval_steps(item_id, zone)
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

    def _generate_retrieval_steps(self, item_id: str, zone: str) -> List[dict]:
        """Generate retrieval steps"""
        return [
            {
                "step": 1,
                "action": "retrieve",
                "item_id": int(item_id),
                "from_position": self.cargo_data[item_id]["position"]["startCoordinates"]
            }
        ]