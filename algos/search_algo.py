from typing import Dict, List, Union, Optional, Tuple, Any
from dataclasses import dataclass
import json
from collections import defaultdict
import re

@dataclass
class Coordinates:
    width: float
    depth: float
    height: float

@dataclass
class Position:
    startCoordinates: Coordinates
    endCoordinates: Coordinates

class ItemSearchSystem:
    def __init__(self, items_data: List[dict], containers_data: List[dict], cargo_data: List[dict]):
        """Initialize search system with data from API endpoint"""
        self.items_data = {
            str(item["item_id"]): {
                "name": item["name"],
                "width": float(item["width_cm"]),
                "depth": float(item["depth_cm"]),
                "height": float(item["height_cm"]),
                "priority": int(item.get("priority", 1)),
                "expiry_date": item.get("expiry_date", ""),
                "usage_limit": int(item.get("usage_limit", 0)),
                "preferred_zone": item.get("preferred_zone", "")
            }
            for item in items_data
        }
        self.zone_to_container = {
            cont["zone"]: str(cont["container_id"]) 
            for cont in containers_data
        }
        
        self.containers = {
            str(cont["container_id"]): {
                "containerId": str(cont["container_id"]),
                "zone": cont["zone"],
                "width": float(cont["width_cm"]),
                "depth": float(cont["depth_cm"]),
                "height": float(cont["height_cm"])
            }
            for cont in containers_data
        }

        # Modified cargo data initialization
        self.cargo_data = {}
        for item in cargo_data:
            item_id = str(item["item_id"])
            coords = re.findall(r'[-+]?\d*\.\d+|[-+]?\d+', item["coordinates"])
            if len(coords) >= 6:
                zone = item["zone"]
                self.cargo_data[item_id] = {
                    "zone": zone,
                    "containerId": self.zone_to_container.get(zone, ""),
                    "position": {
                        "startCoordinates": {
                            "width_cm": float(coords[0]),  # Changed from width to width_cm
                            "depth_cm": float(coords[1]),  # Changed from depth to depth_cm
                            "height_cm": float(coords[2])  # Changed from height to height_cm
                        },
                        "endCoordinates": {
                            "width_cm": float(coords[3]),  # Changed from width to width_cm
                            "depth_cm": float(coords[4]),  # Changed from depth to depth_cm
                            "height_cm": float(coords[5])  # Changed from height to height_cm
                        }
                    }
                }


    def search_by_id(self, item_id: Union[int, str]) -> dict:
        """Search for item by ID, returns API-compatible response"""
        item_id = str(item_id)
        
        if item_id not in self.cargo_data:
            return {
                "success": True,
                "found": False,
                "item": None,
                "retrieval_steps": []
            }
            
        cargo_info = self.cargo_data[item_id]
        zone = cargo_info["zone"]
        container_id = self.zone_to_container.get(zone)
        
        if not container_id:
            return {
                "success": False,
                "found": True,
                "error": f"No container found for zone {zone}",
                "item": None,
                "retrieval_steps": []
            }
            
        return self._prepare_response(item_id, container_id)

    def _prepare_response(self, item_id: str, container_id: str) -> dict:
        """Prepare API-compatible response"""
        item_data = self.items_data[item_id]
        cargo_info = self.cargo_data[item_id]
        container = self.containers[container_id]
        
        return {
            "success": True,
            "found": True,
            "item": {
                "item_id": int(item_id),
                "name": item_data["name"],
                "container_id": container_id,
                "zone": container["zone"],
                "position": cargo_info["position"]
            },
            "retrieval_steps": self._generate_retrieval_steps(item_id, container_id)
        }

    def _generate_retrieval_steps(self, item_id: str, container_id: str) -> List[dict]:
        """Generate retrieval steps in API-compatible format"""
        item_data = self.items_data[item_id]
        cargo_info = self.cargo_data[item_id]
        container = self.containers[container_id]
        
        return [
            {
                "step": 1,
                "action": "locate",
                "item_id": int(item_id),
                "item_name": item_data["name"],
                "from_position": {
                    "width_cm": cargo_info["position"]["startCoordinates"]["width_cm"],
                    "depth_cm": cargo_info["position"]["startCoordinates"]["depth_cm"],
                    "height_cm": cargo_info["position"]["startCoordinates"]["height_cm"]
                }
            },
            {
                "step": 2,
                "action": "retrieve",
                "item_id": int(item_id),
                "item_name": item_data["name"],
                "from_position": {
                    "width_cm": cargo_info["position"]["startCoordinates"]["width_cm"],
                    "depth_cm": cargo_info["position"]["startCoordinates"]["depth_cm"],
                    "height_cm": cargo_info["position"]["startCoordinates"]["height_cm"]
                }
            }
        ]