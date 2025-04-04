from typing import Dict, List, Union, Optional, Tuple, Any
from dataclasses import dataclass
import json
from collections import defaultdict
import sys

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
    def _init_(self, input_data: dict):
        if "items" not in input_data or "containers" not in input_data:
            raise ValueError("Invalid input format: missing 'items' or 'containers' section")
            
        self.items_data = {
            item["item_id"]: {
                "name": item["name"],
                "width": item["width_cm"],
                "depth": item["depth_cm"],
                "height": item["height_cm"],
                "priority": item["priority"],
                "expiry_date": item.get("expiry_date"),
                "usage_limit": item.get("usage_limit"),
                "preferred_zone": item.get("preferred_zone")
            }
            for item in input_data["items"]
        }
        
        self.containers = {
            cont["container_id"]: {
                "containerId": cont["container_id"],
                "zone": cont["zone"],
                "width": cont["width_cm"],
                "depth": cont["depth_cm"],
                "height": cont["height_cm"]
            }
            for cont in input_data["containers"]
        }
        
        self.current_placements = self._generate_placements()
        self.spatial_index = self._build_spatial_index()

    def _generate_placements(self):
        placements = {}
        # Create a list of tuples (item_id, item_data) sorted by priority
        sorted_items = sorted(
            self.items_data.items(),
            key=lambda x: x[1]["priority"],
            reverse=True
        )

        for container_id, container in self.containers.items():
            current_x, current_y, current_z = 0.0, 0.0, 0.0
            max_height_in_row = 0.0
            container_width = container["width"]
            container_depth = container["depth"]
            container_height = container["height"]

            for item_id, item in sorted_items:
                if item_id in placements:
                    continue
                
                width = item["width"]
                depth = item["depth"]
                height = item["height"]

                # Place high-priority items at the front (depth = 0)
                if item["priority"] == 100:
                    current_y = 0.0

                # Check if item fits at current position
                if (current_x + width > container_width):
                    # Move to next row
                    current_x = 0.0
                    current_y += max_height_in_row
                    max_height_in_row = 0.0
                
                if (current_y + depth > container_depth):
                    # Move to next layer
                    current_x = 0.0
                    current_y = 0.0
                    current_z += max_height_in_row
                    max_height_in_row = 0.0
                
                if (current_z + height > container_height):
                    # Item doesn't fit in this container
                    continue

                # Place the item
                placements[item_id] = {
                    "itemId": item_id,
                    "containerId": container_id,
                    "position": {
                        "startCoordinates": {
                            "width": current_x,
                            "depth": current_y,
                            "height": current_z
                        },
                        "endCoordinates": {
                            "width": current_x + width,
                            "depth": current_y + depth,
                            "height": current_z + height
                        }
                    }
                }
                
                current_x += width
                max_height_in_row = max(max_height_in_row, height)

        return placements

    def _build_spatial_index(self):
        index = {
            "item_positions": {},
            "layer_map": defaultdict(lambda: defaultdict(list))
        }
        
        for item_id, placement in self.current_placements.items():
            position = placement["position"]
            container_id = placement["containerId"]
            start = position["startCoordinates"]
            
            index["item_positions"][item_id] = (container_id, position)
            index["layer_map"][container_id][start["depth"]].append(item_id)
        
        return index

    def search_by_id(self, item_id: str):
        try:
            # Try to convert to integer if the keys in items_data are integers
            item_id_converted = int(item_id)
        except ValueError:
            # Keep as string if conversion fails
            item_id_converted = item_id
            
        if item_id_converted not in self.items_data:
            return {
                "success": True,
                "found": False,
                "message": f"Item {item_id} not found in inventory"
            }
            
        # Then check if it has a placement
        if item_id_converted not in self.current_placements:
            return {
                "success": True,
                "found": False,
                "message": f"Item {item_id} exists but not placed in any container"
            }
            
        placement = self.current_placements[item_id_converted]
        container_id = placement["containerId"]
        return self._prepare_response(item_id_converted, container_id)



    def search_by_name(self, item_name: str):
        # Find the item_id for the given name
        item_id = None
        for id, data in self.items_data.items():
            if data["name"].lower() == item_name.lower():
                item_id = id
                break
                
        if item_id is None:
            return {
                "success": True,
                "found": False,
                "message": f"Item with name '{item_name}' not found in inventory"
            }
            
        # Use the search_by_id method to find the placement
        return self.search_by_id(item_id)

    def _find_blocking_items(self, item_id: str, container_id: str):
        if item_id not in self.current_placements:
            return []
            
        target_placement = self.current_placements[item_id]
        target_pos = target_placement["position"]
        target_start = target_pos["startCoordinates"]
        target_end = target_pos["endCoordinates"]
        target_depth = target_start["depth"]
        
        blocking_items = []
        
        for other_id, other_placement in self.current_placements.items():
            if other_id == item_id or other_placement["containerId"] != container_id:
                continue
                
            other_pos = other_placement["position"]
            other_start = other_pos["startCoordinates"]
            other_end = other_pos["endCoordinates"]
            
            if (other_start["depth"] < target_depth and
                other_end["width"] > target_start["width"] and
                other_start["width"] < target_end["width"] and
                other_end["height"] > target_start["height"] and
                other_start["height"] < target_end["height"]):
                blocking_items.append(other_id)
                
        return blocking_items

    def _prepare_response(self, item_id: str, container_id: str):
        item_data = self.items_data[item_id]
        placement = self.current_placements[item_id]
        blocking_items = self._find_blocking_items(item_id, container_id)
        retrieval_steps = self._generate_retrieval_steps(item_id, blocking_items, container_id)
        
        return {
            "success": True,
            "found": True,
            "item": {
                "itemId": item_id,
                "name": item_data["name"],
                "containerId": container_id,
                "zone": self.containers[container_id]["zone"],
                "position": placement["position"]
            },
            "retrievalSteps": retrieval_steps
        }

    def _generate_retrieval_steps(self, item_id: str, blocking_items: List[str], container_id: str):
        steps = []
        
        # If the item has priority 100 or is at the front, no steps needed
        if self.items_data[item_id]["priority"] == 100 or not blocking_items:
            steps.append({
                "step": 1,
                "action": "retrieve",
                "itemId": item_id
            })
            return steps

        steps.append({
            "step": 1,
            "action": "setaside"
        })
        
        for i, blocking_id in enumerate(blocking_items):
            steps.append({
                "step": i + 2,
                "action": "remove",
                "itemId": blocking_id
            })
        
        steps.append({
            "step": len(blocking_items) + 2,
            "action": "retrieve",
            "itemId": item_id
        })
        
        for i, blocking_id in enumerate(reversed(blocking_items)):
            steps.append({
                "step": len(blocking_items) + 3 + i,
                "action": "placeback",
                "itemId": blocking_id
            })
        
        return steps

def get_user_input():
    print("Enter input data (JSON format):")
    
    data = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        data.append(line)
    
    try:
        return json.loads('\n'.join(data))
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        sys.exit(1)

def main():
    try:
        input_data = get_user_input()
        search_system = ItemSearchSystem(input_data)
        
        print("\nContainer Summary:")
        for cont in input_data["containers"]:
            print(f"• {cont['container_id']} ({cont['zone']}): "
                  f"{cont['width_cm']}x{cont['depth_cm']}x{cont['height_cm']} cm")
        
        print("\nSearch Interface (Ctrl+C to exit)")
        while True:
            try:
                search_type = input("\nSearch by:\n1. Item ID\n2. Item Name\nChoice (1/2): ").strip()
                
                if search_type == "1":
                    item_id = input("Enter Item ID: ").strip()
                    response = search_system.search_by_id(item_id)
                elif search_type == "2":
                    item_name = input("Enter Item Name: ").strip()
                    response = search_system.search_by_name(item_name)
                else:
                    print("Invalid choice. Please enter 1 or 2")
                    continue
                
                print("\nSearch Results:")
                print(json.dumps(response, indent=2, default=str))
                
            except KeyboardInterrupt:
                print("\nExiting...")
                break
                
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if _name_ == "_main_":
    main()