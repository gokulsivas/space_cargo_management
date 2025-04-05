import json
import re
import csv
import os
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
import polars as pl
from datetime import datetime
from schemas import Position, ReturnPlanRequest, ReturnPlanResponse, ReturnItem, ReturnPlanStep, RetrievalStep, CompleteUndockingRequest, Object3D, ReturnManifest
import httpx
from algos.search_algo import ItemSearchSystem
from algos.waste_algo import (
    load_waste_items,
    load_imported_items,
    link_waste_with_imported_items,
    select_waste_items_greedy,
    generate_return_plan as generate_return_plan_steps,
    create_return_manifest
)

router = APIRouter(
    prefix="/api/waste",
    tags=["waste"],
)

async def search_retrieve(item_id: int, zone: str) -> dict:
    """Call the search endpoint to get retrieval steps for an item."""
    print(f"\nCalling search endpoint for item {item_id} in zone {zone}")
    async with httpx.AsyncClient() as client:
        try:
            # First, check if the item exists in the cargo arrangement data
            cargo_df = pl.read_csv("cargo_arrangement.csv")
            # Convert item_id to string for comparison
            item_data = cargo_df.filter(pl.col("item_id").cast(str) == str(item_id)).to_dicts()
            
            if not item_data:
                print(f"Item {item_id} not found in cargo arrangement data")
                return {"success": False, "found": False, "retrieval_steps": []}
            
            # Get the container ID from the cargo arrangement data
            container_id = item_data[0]["container_id"]
            print(f"Found item {item_id} in container {container_id}")
            
            # Convert item_id to integer for the URL
            url = f"http://localhost:8000/api/search?item_id={int(item_id)}"
            print(f"Making request to: {url}")
            response = await client.get(url)
            print(f"Response status code: {response.status_code}")
            print(f"Response body: {response.text}")
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Search endpoint returned status code: {response.status_code}")
                return {"success": False, "found": False, "retrieval_steps": []}
        except Exception as e:
            print(f"Error calling search endpoint: {str(e)}")
            print(f"Error type: {type(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return {"success": False, "found": False, "retrieval_steps": []}

def parse_position(position_str: str) -> dict:
    """
    Parse a position string formatted as:
    "(x,y,z),(x,y,z)"
    and return a dict with startCoordinates and endCoordinates.
    """
    pattern = r"\((.*?)\)"
    matches = re.findall(pattern, position_str)

    if len(matches) != 2:
        return {
            "startCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0},
            "endCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0}
        }

    try:
        def parse_tuple(tuple_str: str) -> dict:
            values = [float(v) for v in tuple_str.split(",")]
            return {"width_cm": values[0], "depth_cm": values[1], "height_cm": values[2]}
        
        start_coords = parse_tuple(matches[0])
        end_coords = parse_tuple(matches[1])
        
        return {
            "startCoordinates": start_coords,
            "endCoordinates": end_coords
        }
    except Exception as e:
        print(f"Error parsing position tuple: {str(e)}")
        return {
            "startCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0},
            "endCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0}
        }

@router.get("/identify")
async def identify_waste():
    waste_file = "waste_items.csv"
    imported_file = "imported_items.csv"
    waste_items = []
    new_waste_items = []  # To track newly identified waste items for appending

    # Load existing waste items from waste_items.csv if it exists.
    if os.path.exists(waste_file):
        try:
            waste_df = pl.read_csv(waste_file)
            if not waste_df.is_empty():
                for item in waste_df.to_dicts():
                    position_value = item.get("position", "")
                    if isinstance(position_value, str):
                        if position_value.strip().startswith("{"):
                            try:
                                position_dict = json.loads(position_value)
                            except Exception as e:
                                print(f"JSON parsing error: {str(e)}")
                                position_dict = {
                                    "startCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0},
                                    "endCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0}
                                }
                        elif position_value.strip().startswith("("):
                            position_dict = parse_position(position_value)
                        else:
                            position_dict = {
                                "startCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0},
                                "endCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0}
                            }
                    else:
                        position_dict = {
                            "startCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0},
                            "endCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0}
                        }
                    
                    position_model = Position(
                        startCoordinates=position_dict.get("startCoordinates", {"width_cm": 0, "depth_cm": 0, "height_cm": 0}),
                        endCoordinates=position_dict.get("endCoordinates", {"width_cm": 0, "depth_cm": 0, "height_cm": 0})
                    )
                    
                    # Fix: Ensure item_id is cast to int safely with default value
                    try:
                        item_id = int(item.get("item_id", "0"))
                    except ValueError:
                        item_id = 0
                    
                    formatted_item = {
                        "item_id": item_id,
                        "name": str(item.get("name", "")),
                        "reason": str(item.get("reason", "")),
                        "container_id": str(item.get("container_id", "")),
                        "position": position_model.dict(),
                        "retrieval_steps": json.loads(item.get("retrieval_steps", "[]"))
                    }
                    waste_items.append(formatted_item)
        except Exception as e:
            print(f"Error reading waste_items.csv: {str(e)}")
    
    # Now, check imported_items.csv for expired items.
    if os.path.exists(imported_file):
        try:
            imported_df = pl.read_csv(imported_file)
            current_date = datetime.now().date()
            print(f"Current date: {current_date}")
            
            # Check for items with usage_limit = 0
            if "usage_limit" in imported_df.columns:
                zero_usage_limit_df = imported_df.filter(
                    (pl.col("usage_limit").is_not_null()) & 
                    (pl.col("usage_limit") == 0)
                )
                
                print(f"Found {len(zero_usage_limit_df)} items with usage_limit = 0")
                
                for item in zero_usage_limit_df.to_dicts():
                    print(f"Processing item with usage_limit = 0: {item}")
                    # Lookup container_id from cargo_arrangement.csv first
                    container_id = ""
                    position_str = "(0,0,0),(0,0,0)"  # Default value for CSV
                    retrieval_steps = []
                    # Initialize coordinates with default values
                    coordinates = {
                        "startCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0},
                        "endCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0}
                    }
                    
                    if os.path.exists("cargo_arrangement.csv"):
                        try:
                            cargo_df = pl.read_csv("cargo_arrangement.csv")
                            # Fix: Cast both sides to string for comparison
                            cargo_matching = cargo_df.filter(pl.col("item_id").cast(pl.Utf8) == str(item.get("item_id", ""))).to_dicts()
                            if cargo_matching:
                                container_id = str(cargo_matching[0].get("container_id", ""))
                                pos_str = cargo_matching[0].get("coordinates", "")
                                if pos_str:
                                    coordinates = parse_position(pos_str)
                                    position_str = pos_str
                                    
                                # Calculate retrieval steps
                                items_in_container = cargo_df.filter(
                                    (pl.col("container_id") == container_id) & 
                                    (pl.col("item_id").cast(str) != str(item.get("item_id", "")))
                                ).to_dicts()
                                
                                # Sort items by depth (front to back)
                                items_in_container.sort(key=lambda x: float(x["coordinates"].split(",")[1]))
                                
                                step_number = 1
                                
                                # Remove blocking items (front to back)
                                for blocking_item in items_in_container:
                                    retrieval_steps.append({
                                        "step": step_number,
                                        "action": "remove",
                                        "item_id": int(blocking_item["item_id"]),
                                        "item_name": blocking_item["name"]
                                    })
                                    step_number += 1
                                    
                                # Retrieve target item
                                retrieval_steps.append({
                                    "step": step_number,
                                    "action": "retrieve",
                                    "item_id": int(item.get("item_id", "0")),
                                    "item_name": item.get("name", "")
                                })
                                step_number += 1
                                
                                # Place back blocking items (back to front)
                                for blocking_item in reversed(items_in_container):
                                    retrieval_steps.append({
                                        "step": step_number,
                                        "action": "place",
                                        "item_id": int(blocking_item["item_id"]),
                                        "item_name": blocking_item["name"]
                                    })
                                    step_number += 1
                        except Exception as e:
                            print(f"Error reading cargo_arrangement.csv: {str(e)}")
                    
                    # Only if not found in cargo_arrangement.csv, try imported_containers.csv
                    if not container_id and os.path.exists("imported_containers.csv"):
                        try:
                            containers_df = pl.read_csv("imported_containers.csv")
                            # Assume imported_containers.csv has columns: container_id, zone, ...
                            matching_container = containers_df.filter(pl.col("zone") == item.get("preferred_zone", "")).to_dicts()
                            if matching_container:
                                container_id = str(matching_container[0].get("container_id", ""))
                        except Exception as e:
                            print(f"Error reading imported_containers.csv: {str(e)}")
                    
                    # Fix: Ensure item_id is cast to int safely with default value
                    try:
                        item_id = int(item.get("item_id", "0"))
                    except ValueError:
                        item_id = 0
                    
                    # Create the formatted item for the API response
                    position_model = Position(
                        startCoordinates=coordinates.get("startCoordinates", {"width_cm": 0, "depth_cm": 0, "height_cm": 0}),
                        endCoordinates=coordinates.get("endCoordinates", {"width_cm": 0, "depth_cm": 0, "height_cm": 0})
                    )
                    
                    item_name = str(item.get("name", ""))
                    
                    zero_usage_item = {
                        "item_id": item_id,
                        "name": item_name,
                        "reason": "Usage Limit is 0",
                        "container_id": container_id,
                        "position": position_model.dict(),
                        "retrieval_steps": retrieval_steps
                    }
                    
                    # Create a simple dictionary for CSV export
                    csv_item = {
                        "item_id": item_id,
                        "name": item_name,
                        "reason": "Usage Limit is 0",
                        "container_id": container_id,
                        "position": position_str,
                        "retrieval_steps": json.dumps(retrieval_steps)
                    }
                    
                    # Only add to waste items if not already there
                    if not any(w["item_id"] == zero_usage_item["item_id"] for w in waste_items):
                        print(f"Adding item with usage_limit = 0 to waste items: {zero_usage_item}")
                        waste_items.append(zero_usage_item)
                        new_waste_items.append(csv_item)
            
            # Check for expired dates
            if "expiry_date" in imported_df.columns:
                # Try parsing dates in both formats using Polars
                # First try YYYY-MM-DD format
                try:
                    expired_df = imported_df.filter(
                        (pl.col("expiry_date").is_not_null()) & 
                        (pl.col("expiry_date").str.len_chars() > 0) &
                        (pl.col("expiry_date").str.strptime(pl.Date, format="%Y-%m-%d", strict=False) < current_date)
                    )
                except Exception as e:
                    print(f"Error parsing YYYY-MM-DD format: {str(e)}")
                    # If that fails, try DD-MM-YY format
                    try:
                        expired_df = imported_df.filter(
                            (pl.col("expiry_date").is_not_null()) & 
                            (pl.col("expiry_date").str.len_chars() > 0) &
                            (pl.col("expiry_date").str.strptime(pl.Date, format="%d-%m-%y", strict=False) < current_date)
                        )
                    except Exception as e:
                        print(f"Error parsing DD-MM-YY format: {str(e)}")
                        expired_df = pl.DataFrame()  # Empty DataFrame if both formats fail
                
                print(f"Found {len(expired_df)} items with expired dates")
                
                for item in expired_df.to_dicts():
                    print(f"Processing expired item: {item}")
                    # Lookup container_id from cargo_arrangement.csv first
                    container_id = ""
                    position_str = "(0,0,0),(0,0,0)"  # Default value for CSV
                    retrieval_steps = []
                    # Initialize coordinates with default values
                    coordinates = {
                        "startCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0},
                        "endCoordinates": {"width_cm": 0, "depth_cm": 0, "height_cm": 0}
                    }
                    
                    if os.path.exists("cargo_arrangement.csv"):
                        try:
                            cargo_df = pl.read_csv("cargo_arrangement.csv")
                            # Fix: Cast both sides to string for comparison
                            cargo_matching = cargo_df.filter(pl.col("item_id").cast(pl.Utf8) == str(item.get("item_id", ""))).to_dicts()
                            if cargo_matching:
                                container_id = str(cargo_matching[0].get("container_id", ""))
                                pos_str = cargo_matching[0].get("coordinates", "")
                                if pos_str:
                                    coordinates = parse_position(pos_str)
                                    position_str = pos_str
                                    
                                # Calculate retrieval steps
                                items_in_container = cargo_df.filter(
                                    (pl.col("container_id") == container_id) & 
                                    (pl.col("item_id").cast(str) != str(item.get("item_id", "")))
                                ).to_dicts()
                                
                                # Sort items by depth (front to back)
                                items_in_container.sort(key=lambda x: float(x["coordinates"].split(",")[1]))
                                
                                step_number = 1
                                
                                # Remove blocking items (front to back)
                                for blocking_item in items_in_container:
                                    retrieval_steps.append({
                                        "step": step_number,
                                        "action": "remove",
                                        "item_id": int(blocking_item["item_id"]),
                                        "item_name": blocking_item["name"]
                                    })
                                    step_number += 1
                                    
                                # Retrieve target item
                                retrieval_steps.append({
                                    "step": step_number,
                                    "action": "retrieve",
                                    "item_id": int(item.get("item_id", "0")),
                                    "item_name": item.get("name", "")
                                })
                                step_number += 1
                                
                                # Place back blocking items (back to front)
                                for blocking_item in reversed(items_in_container):
                                    retrieval_steps.append({
                                        "step": step_number,
                                        "action": "place",
                                        "item_id": int(blocking_item["item_id"]),
                                        "item_name": blocking_item["name"]
                                    })
                                    step_number += 1
                        except Exception as e:
                            print(f"Error reading cargo_arrangement.csv: {str(e)}")
                    
                    # Only if not found in cargo_arrangement.csv, try imported_containers.csv
                    if not container_id and os.path.exists("imported_containers.csv"):
                        try:
                            containers_df = pl.read_csv("imported_containers.csv")
                            # Assume imported_containers.csv has columns: container_id, zone, ...
                            matching_container = containers_df.filter(pl.col("zone") == item.get("preferred_zone", "")).to_dicts()
                            if matching_container:
                                container_id = str(matching_container[0].get("container_id", ""))
                        except Exception as e:
                            print(f"Error reading imported_containers.csv: {str(e)}")
                    
                    # Fix: Ensure item_id is cast to int safely with default value
                    try:
                        item_id = int(item.get("item_id", "0"))
                    except ValueError:
                        item_id = 0
                    
                    # Create the formatted item for the API response
                    position_model = Position(
                        startCoordinates=coordinates.get("startCoordinates", {"width_cm": 0, "depth_cm": 0, "height_cm": 0}),
                        endCoordinates=coordinates.get("endCoordinates", {"width_cm": 0, "depth_cm": 0, "height_cm": 0})
                    )
                    
                    item_name = str(item.get("name", ""))
                    
                    expired_item = {
                        "item_id": item_id,
                        "name": item_name,
                        "reason": "Expired",
                        "container_id": container_id,
                        "position": position_model.dict(),
                        "retrieval_steps": retrieval_steps
                    }
                    
                    # Create a simple dictionary for CSV export
                    csv_item = {
                        "item_id": item_id,
                        "name": item_name,
                        "reason": "Expired",
                        "container_id": container_id,
                        "position": position_str,
                        "retrieval_steps": json.dumps(retrieval_steps)
                    }
                    
                    # Only add to waste items if not already there
                    if not any(w["item_id"] == expired_item["item_id"] for w in waste_items):
                        print(f"Adding expired item to waste items: {expired_item}")
                        waste_items.append(expired_item)
                        new_waste_items.append(csv_item)
            
            # Now append the new waste items to waste_items.csv
            if new_waste_items:
                print(f"Appending {len(new_waste_items)} new waste items to waste_items.csv")
                
                # If the waste file exists, read it and combine with new items
                if os.path.exists(waste_file):
                    try:
                        # Read existing items
                        existing_items = []
                        with open(waste_file, 'r') as f:
                            reader = csv.DictReader(f)
                            existing_items = list(reader)
                            print(f"Found {len(existing_items)} existing items in waste_items.csv")
                        
                        # Add new items that aren't already in the file
                        existing_item_ids = {item['item_id'] for item in existing_items}
                        new_items_added = 0
                        for new_item in new_waste_items:
                            if str(new_item['item_id']) not in existing_item_ids:
                                existing_items.append(new_item)
                                new_items_added += 1
                        
                        print(f"Adding {new_items_added} new items to waste_items.csv")
                        
                        # Write all items back to the file
                        with open(waste_file, 'w', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=['item_id', 'name', 'reason', 'container_id', 'position', 'retrieval_steps'])
                            writer.writeheader()
                            writer.writerows(existing_items)
                        
                        print(f"Successfully wrote {len(existing_items)} items to waste_items.csv")
                    except Exception as e:
                        print(f"Error appending to waste_items.csv: {str(e)}")
                        print(f"Error type: {type(e)}")
                        import traceback
                        print(f"Traceback: {traceback.format_exc()}")
                else:
                    print("Creating new waste_items.csv")
                    # Create new file with waste items
                    try:
                        with open(waste_file, 'w', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=['item_id', 'name', 'reason', 'container_id', 'position', 'retrieval_steps'])
                            writer.writeheader()
                            writer.writerows(new_waste_items)
                        print(f"Successfully created waste_items.csv with {len(new_waste_items)} items")
                    except Exception as e:
                        print(f"Error creating waste_items.csv: {str(e)}")
                        print(f"Error type: {type(e)}")
                        import traceback
                        print(f"Traceback: {traceback.format_exc()}")
                    
        except Exception as e:
            print(f"Error processing imported_items.csv for expiry: {str(e)}")
    
    return {"success": True, "wasteItems": waste_items}

def calculate_volume(obj):
    width = abs(obj.end["width_cm"] - obj.start["width_cm"])
    depth = abs(obj.end["depth_cm"] - obj.start["depth_cm"])
    height = abs(obj.end["height_cm"] - obj.start["height_cm"])
    return width * depth * height

def read_waste_data(waste_filename, imported_filename):
    print(f"\nReading waste data from {waste_filename}")
    objects = []
    imported_items = load_imported_items(imported_filename)  # Use the function from waste_algo.py
    print(f"Loaded imported items: {imported_items}")
    weights = {}

    if not os.path.exists(waste_filename):
        print(f"Warning: {waste_filename} does not exist")
        return objects, weights
    
    try:
        waste_df = pl.read_csv(waste_filename)
        if waste_df.is_empty():
            print("Waste file is empty")
            return objects, weights
            
        for row in waste_df.to_dicts():
            print(f"\nProcessing row: {row}")
            
            # Get and validate item_id
            item_id = str(row.get("item_id", "")).strip()
            if not item_id:
                print(f"Skipping row with empty item_id: {row}")
                continue
            print(f"Processing item_id: {item_id}")
            
            # Get and validate container_id
            container_id = str(row.get("container_id", "")).strip()
            if not container_id:
                print(f"Skipping row with empty container_id: {row}")
                continue
            print(f"Container_id: {container_id}")
            
            # Parse position
            position_str = str(row.get("position", ""))
            coordinates = parse_position(position_str)
            print(f"Parsed coordinates: {coordinates}")
            
            # Get weight from imported items
            weight = imported_items.get(item_id, 0)
            print(f"Found weight: {weight}")
            
            # Create Object3D with positional parameters
            obj = Object3D(
                item_id,
                str(row.get("name", "")),
                container_id,
                coordinates["startCoordinates"],
                coordinates["endCoordinates"]
            )
            print(f"Created Object3D: {obj.__dict__}")
            objects.append(obj)
            weights[item_id] = weight

    except Exception as e:
        print(f"Error reading waste data: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return objects, weights

    print(f"\nTotal objects read: {len(objects)}")
    print(f"Total weights: {weights}")
    return objects, weights

def calculate_retrieval_steps(item_id: int, container_id: str, cargo_df: pl.DataFrame, containers_df: pl.DataFrame) -> List[Dict]:
    """Calculate the steps needed to retrieve an item from a container."""
    print(f"\nCalculating retrieval steps for item {item_id} in container {container_id}")
    
    try:
        # Read imported items data for item details
        imported_df = pl.read_csv("imported_items.csv")
        print(f"Read imported items data with {len(imported_df)} rows")
        
        # Convert DataFrames to lists of dictionaries for ItemSearchSystem
        items_data = []
        for item in imported_df.to_dicts():
            items_data.append({
                "item_id": str(item.get("item_id", "")),
                "name": str(item.get("name", "")),
                "width_cm": float(item.get("width_cm", 0)),
                "depth_cm": float(item.get("depth_cm", 0)),
                "height_cm": float(item.get("height_cm", 0)),
                "priority": int(item.get("priority", 1)),
                "usage_limit": int(item.get("usage_limit", 0))
            })
            
        containers_data = containers_df.to_dicts()
        
        # Convert cargo data with proper position format
        cargo_data = []
        for item in cargo_df.to_dicts():
            position_str = item.get("coordinates", "")
            if position_str:
                try:
                    coords = [float(x) for x in position_str.replace('(', '').replace(')', '').split(',')]
                    if len(coords) >= 6:
                        cargo_data.append({
                            "item_id": str(item.get("item_id", "")),
                            "container_id": str(item.get("container_id", "")),
                            "zone": str(item.get("zone", "")),
                            "coordinates": position_str
                        })
                except Exception as e:
                    print(f"Error parsing coordinates for item {item.get('item_id', '')}: {str(e)}")
        
        # Create ItemSearchSystem instance
        search_system = ItemSearchSystem(
            items_data=items_data,
            containers_data=containers_data,
            cargo_data=cargo_data
        )
        
        # Search for the item using the optimized algorithm
        result = search_system.search_by_id(item_id)
        
        if not result.get("success", False) or not result.get("found", False):
            print(f"Item {item_id} not found or error in search: {result.get('message', '')}")
            return []
            
        # Convert the retrieval steps to the required format
        steps = []
        for step in result.get("retrieval_steps", []):
            steps.append({
                "action": step["action"],
                "item_id": str(step["item_id"]),
                "item_name": step.get("item_name", ""),
                "container_id": container_id,
                "zone": result.get("item", {}).get("zone", "")
            })
        
        print(f"Generated {len(steps)} retrieval steps")
        return steps
        
    except Exception as e:
        print(f"Error calculating retrieval steps: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return []

# Response models
class ReturnManifest(BaseModel):
    undocking_container_id: str
    undocking_date: str
    return_items: List[ReturnItem]
    total_volume: float
    total_weight: float

class ReturnPlanResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    return_plan: List[ReturnPlanStep] = Field(default_factory=list)
    retrieval_steps: List[RetrievalStep] = Field(default_factory=list)
    return_manifest: ReturnManifest

@router.post("/return-plan", response_model=ReturnPlanResponse)
async def generate_return_plan(request: ReturnPlanRequest):
    """Generate a return plan for waste items."""
    try:
        print("\nGenerating return plan...")
        print(f"Request: {request}")
        
        # Extract request data
        undocking_container_id = request.undocking_container_id
        undocking_date = request.undocking_date
        max_weight = float(request.max_weight) if request.max_weight else float('inf')
        
        # Load waste items and imported items data using the functions from waste_algo.py
        waste_items = load_waste_items()  # Using default filename
        imported_items = load_imported_items()  # Using default filename
        
        print(f"Loaded {len(waste_items)} waste items")
        print(f"Loaded {len(imported_items)} imported items")
        
        # Link waste items with their weights from imported items
        linked_items = link_waste_with_imported_items(waste_items, imported_items)
        print(f"Linked {len(linked_items)} items")
        
        # Filter items for the specified container
        container_items = [item for item in linked_items if item["container_id"] == undocking_container_id]
        print(f"Found {len(container_items)} items in container {undocking_container_id}")
        
        if not container_items:
            print(f"No items found in container {undocking_container_id}")
            return ReturnPlanResponse(
                success=True,
                return_plan=[],
                retrieval_steps=[],
                return_manifest=ReturnManifest(
                    undocking_container_id=undocking_container_id,
                    undocking_date=undocking_date,
                    return_items=[],
                    total_volume=0,
                    total_weight=0
                )
            )
        
        # Select optimal set of waste items using greedy approach
        selected_items, total_weight = select_waste_items_greedy(container_items, max_weight)
        print(f"Selected {len(selected_items)} items with total weight {total_weight} kg")
        
        # Generate return plan and retrieval steps using the renamed function
        return_plan, retrieval_steps = generate_return_plan_steps(selected_items, undocking_container_id)
        print(f"Generated {len(return_plan)} return plan steps")
        print(f"Generated {len(retrieval_steps)} retrieval steps")
        
        # Convert return plan steps to ReturnPlanStep objects
        return_plan_steps = []
        for step in return_plan:
            return_plan_steps.append(ReturnPlanStep(
                step=step["step"],
                item_id=str(step["itemId"]),
                item_name=step["itemName"],
                from_container=step["fromContainer"],
                to_container=step["toContainer"]
            ))
        
        # Convert retrieval steps to RetrievalStep objects
        retrieval_step_objects = []
        for step in retrieval_steps:
            retrieval_step_objects.append(RetrievalStep(
                step=step["step"],
                action=step["action"],
                item_id=int(step["itemId"]),
                item_name=step["itemName"]
            ))
        
        # Create return manifest
        return_manifest = create_return_manifest(
            selected_items, 
            undocking_container_id, 
            undocking_date, 
            total_weight
        )
        print(f"Created return manifest with {len(return_manifest['returnItems'])} items")
        
        # Convert return items to ReturnItem objects
        return_items = []
        for item in return_manifest["returnItems"]:
            return_items.append(ReturnItem(
                item_id=str(item["itemId"]),
                name=item["name"],
                reason=item["reason"]
            ))
        
        return ReturnPlanResponse(
            success=True,
            return_plan=return_plan_steps,
            retrieval_steps=retrieval_step_objects,
            return_manifest=ReturnManifest(
                undocking_container_id=undocking_container_id,
                undocking_date=undocking_date,
                return_items=return_items,
                total_volume=return_manifest["totalVolume"],
                total_weight=return_manifest["totalWeight"]
            )
        )
        
    except Exception as e:
        print(f"Error generating return plan: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return ReturnPlanResponse(
            success=False,
            error=str(e),
            return_plan=[],
            retrieval_steps=[],
            return_manifest=ReturnManifest(
                undocking_container_id=request.undocking_container_id if request else None,
                undocking_date=request.undocking_date if request else None,
                return_items=[],
                total_volume=0,
                total_weight=0
            )
        )

@router.post("/complete-undocking")
async def complete_undocking(request: CompleteUndockingRequest):
    waste_file = "waste_items.csv"
    items_file = "imported_items.csv"
    items_count = 0
    
    # First, handle existing waste items
    existing_waste_items = []
    if os.path.exists(waste_file):
        try:
            waste_items_df = pl.read_csv(waste_file)
            if not waste_items_df.is_empty():
                # Keep only items that are NOT in the undocking container
                existing_waste_items = waste_items_df.filter(
                    pl.col("container_id") != request.undocking_container_id
                ).to_dicts()
                # Count items being removed
                items_count = waste_items_df.filter(
                    pl.col("container_id") == request.undocking_container_id
                ).height
                
                # Write back the filtered waste items
                if existing_waste_items:
                    waste_df = pl.DataFrame(existing_waste_items)
                    waste_df.write_csv(waste_file)
                else:
                    # If no items left, delete the file
                    os.remove(waste_file)
        except Exception as e:
            print(f"Error processing waste items: {str(e)}")
    
    # Then handle items that have reached their usage limit
    if os.path.exists(items_file):
        try:
            items_df = pl.read_csv(items_file)
            if "usage_count" in items_df.columns and "usage_limit" in items_df.columns:
                # Check for items that have reached their usage limit OR have a usage limit of 0
                expired_items = items_df.filter(
                    ((pl.col("usage_count") >= pl.col("usage_limit")) | 
                     (pl.col("usage_limit") == 0)) & 
                    (pl.col("container_id") == request.undocking_container_id)
                )
                
                if not expired_items.is_empty():
                    # Remove items that have reached their usage limit OR have a usage limit of 0
                    items_df = items_df.filter(
                        ~(((pl.col("usage_count") >= pl.col("usage_limit")) | 
                           (pl.col("usage_limit") == 0)) & 
                          (pl.col("container_id") == request.undocking_container_id))
                    )
                    items_df.write_csv(items_file)
        
        except Exception as e:
            print(f"Error processing items at usage limit: {str(e)}")
    
    return {"success": True, "items_removed": items_count}