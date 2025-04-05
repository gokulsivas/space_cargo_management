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
            if "expiry_date" in imported_df.columns:
                current_date = datetime.now().date()
                print(f"Current date: {current_date}")
                
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
                # Create the DataFrame with new waste items
                new_waste_df = pl.DataFrame(new_waste_items)
                print(f"New waste items DataFrame: {new_waste_df}")
                
                # If the waste file exists, append to it, otherwise create it
                if os.path.exists(waste_file):
                    print(f"Reading existing waste_items.csv")
                    # Read existing file
                    try:
                        existing_waste_df = pl.read_csv(waste_file)
                        print(f"Existing waste items: {existing_waste_df}")
                        # Concatenate and write back
                        combined_df = pl.concat([existing_waste_df, new_waste_df])
                        print(f"Combined DataFrame: {combined_df}")
                        combined_df.write_csv(waste_file)
                        print("Successfully wrote to waste_items.csv")
                    except Exception as e:
                        print(f"Error appending to waste_items.csv: {str(e)}")
                        print(f"Error type: {type(e)}")
                        import traceback
                        print(f"Traceback: {traceback.format_exc()}")
                        # If error reading, just write the new items
                        new_waste_df.write_csv(waste_file)
                else:
                    print("Creating new waste_items.csv")
                    # Create new file with waste items
                    new_waste_df.write_csv(waste_file)
                    
        except Exception as e:
            print(f"Error processing imported_items.csv for expiry: {str(e)}")
    
    return {"success": True, "wasteItems": waste_items}

def calculate_volume(obj):
    width = abs(obj.end["width_cm"] - obj.start["width_cm"])
    depth = abs(obj.end["depth_cm"] - obj.start["depth_cm"])
    height = abs(obj.end["height_cm"] - obj.start["height_cm"])
    return width * depth * height

def load_imported_items(filename):
    print(f"\nLoading imported items from {filename}")
    imported_items = {}
    if not os.path.exists(filename):
        print(f"Warning: {filename} does not exist")
        return imported_items
    
    with open(filename, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Get item_id and ensure it's not empty
            item_id = str(row.get("item_id", "")).strip()
            if not item_id:
                print(f"Skipping row with empty item_id: {row}")
                continue
                
            # Get mass and convert to float
            try:
                mass = float(row.get("mass", 0))
            except ValueError:
                print(f"Invalid mass value for item {item_id}: {row.get('mass')}")
                mass = 0
                
            print(f"Loaded item {item_id} with mass {mass}")
            imported_items[item_id] = mass
    
    print(f"Loaded {len(imported_items)} imported items")
    return imported_items

def read_waste_data(waste_filename, imported_filename):
    print(f"\nReading waste data from {waste_filename}")
    objects = []
    imported_items = load_imported_items(imported_filename)
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
    totalVolume: float = 0
    totalWeight: float = 0
    undockingContainerId: Optional[str] = None
    undockingDate: Optional[str] = None

class ReturnPlanResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    returnPlan: List[Dict] = Field(default_factory=list)
    retrievalSteps: List[Dict] = Field(default_factory=list)
    returnManifest: ReturnManifest = Field(default_factory=ReturnManifest)

@router.post("/return-plan", response_model=ReturnPlanResponse)
async def generate_return_plan(request: ReturnPlanRequest):
    """Generate a return plan for waste items."""
    try:
        print("\nGenerating return plan...")
        print(f"Request: {request}")
        
        # Read waste items data
        waste_df = pl.read_csv("waste_items.csv")
        print(f"Read waste items data with {len(waste_df)} rows")
        print(f"Waste items: {waste_df}")
        
        # Read imported items data for weights
        imported_df = pl.read_csv("imported_items.csv")
        print(f"Read imported items data with {len(imported_df)} rows")
        
        # Read cargo arrangement data - prefer temp file if it exists
        cargo_file = "cargo_arrangement.csv"
        temp_cargo_file = "temp_cargo_arrangement.csv"
        
        if os.path.exists(temp_cargo_file):
            print(f"Using temp cargo file: {temp_cargo_file}")
            cargo_df = pl.read_csv(temp_cargo_file)
        else:
            print(f"Using main cargo file: {cargo_file}")
            cargo_df = pl.read_csv(cargo_file)
            
        print(f"Read cargo arrangement data with {len(cargo_df)} rows")
        
        # Read containers data
        containers_df = pl.read_csv("imported_containers.csv")
        print(f"Read containers data with {len(containers_df)} rows")
        
        # Filter waste items in the specified container
        request_container_id = request.undockingContainerId.strip()
        print(f"Filtering waste items for container: '{request_container_id}'")
        waste_items = waste_df.filter(
            pl.col("container_id").str.strip_chars().eq(request_container_id)
        )
        
        print(f"Found {len(waste_items)} waste items in container {request_container_id}")
        print(f"Filtered waste items: {waste_items}")
        
        # Calculate total weight using Polars join
        total_weight = 0
        total_volume = 0
        return_items = []
        all_retrieval_steps = []
        
        if not waste_items.is_empty():
            print("Processing waste items...")
            # Join waste items with imported items to get weights
            joined_df = waste_items.join(
                imported_df,
                left_on="item_id",
                right_on="item_id",
                how="left"
            )
            
            print(f"Joined data: {joined_df}")
            
            # Sum up the mass_kg values
            total_weight = joined_df["mass_kg"].sum()
            print(f"Total weight: {total_weight} kg")
            
            # Calculate total volume from cargo arrangement data
            for item in waste_items.to_dicts():
                item_id = str(item.get('item_id', '')).strip()
                print(f"Processing waste item ID: {item_id}")
                if not item_id:
                    print("Skipping item with empty ID")
                    continue
                
                # Find the item in cargo arrangement to get accurate coordinates
                item_cargo = cargo_df.filter(
                    pl.col("item_id").cast(str).str.strip_chars().eq(item_id)
                ).to_dicts()
                
                print(f"Cargo data for item {item_id}: {item_cargo}")
                
                if item_cargo:
                    coords_str = item_cargo[0].get("coordinates", "")
                    if coords_str:
                        try:
                            # Parse coordinates from format like "(0,0,0),(15.7,18.6,29.4)"
                            coords = re.findall(r'[-+]?\d*\.\d+|[-+]?\d+', coords_str)
                            if len(coords) >= 6:
                                # Extract dimensions from coordinates
                                width = abs(float(coords[3]) - float(coords[0]))
                                depth = abs(float(coords[4]) - float(coords[1]))
                                height = abs(float(coords[5]) - float(coords[2]))
                                
                                # Calculate item volume
                                item_volume = width * depth * height
                                total_volume += item_volume
                                print(f"Item {item_id} volume: {item_volume} cubic cm")
                        except Exception as e:
                            print(f"Error calculating volume for item {item_id}: {str(e)}")
                else:
                    print(f"No cargo data found for item {item_id}")
                    # Try to get dimensions from imported_items for items removed from cargo
                    item_import = imported_df.filter(
                        pl.col("item_id").cast(str).str.strip_chars().eq(item_id)
                    ).to_dicts()
                    
                    if item_import:
                        try:
                            # Calculate volume from imported items dimensions
                            width = float(item_import[0].get("width_cm", 0))
                            depth = float(item_import[0].get("depth_cm", 0))
                            height = float(item_import[0].get("height_cm", 0))
                            
                            # Calculate item volume
                            item_volume = width * depth * height
                            total_volume += item_volume
                            print(f"Item {item_id} volume (from imported data): {item_volume} cubic cm")
                        except Exception as e:
                            print(f"Error calculating volume from imported data for item {item_id}: {str(e)}")
            
            print(f"Total volume: {total_volume} cubic cm")
            
            # Prepare data for ItemSearchSystem
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
            
            containers_data = []
            for cont in containers_df.to_dicts():
                containers_data.append({
                    "container_id": str(cont.get("container_id", "")),
                    "zone": str(cont.get("zone", "")),
                    "width_cm": float(cont.get("width_cm", 0)),
                    "depth_cm": float(cont.get("depth_cm", 0)),
                    "height_cm": float(cont.get("height_cm", 0))
                })
            
            cargo_data = []
            for item in cargo_df.to_dicts():
                cargo_data.append({
                    "item_id": str(item.get("item_id", "")),
                    "container_id": str(item.get("container_id", "")),
                    "zone": str(item.get("zone", "")),
                    "coordinates": str(item.get("coordinates", ""))
                })
            
            # Create ItemSearchSystem instance
            search_system = ItemSearchSystem(
                items_data=items_data,
                containers_data=containers_data,
                cargo_data=cargo_data
            )
            
            # Process each waste item
            for item in waste_items.to_dicts():
                item_id = str(item.get('item_id', '')).strip()
                if not item_id:
                    continue
                
                print(f"\nProcessing item {item_id}")
                
                # Search for the item using the optimized algorithm
                result = search_system.search_by_id(item_id)
                print(f"Search result: {result}")
                
                if result.get("success", False) and result.get("found", False):
                    retrieval_steps = result.get("retrieval_steps", [])
                    
                    if retrieval_steps:
                        # Add retrieval steps with container info
                        for step in retrieval_steps:
                            all_retrieval_steps.append({
                                "action": step["action"],
                                "item_id": str(step["item_id"]),
                                "item_name": step.get("item_name", ""),
                                "container_id": request_container_id,
                                "zone": result.get("item", {}).get("zone", "")
                            })
                    else:
                        # If no steps provided, create a simple one-step retrieval
                        all_retrieval_steps.append({
                            "action": "retrieve",
                            "item_id": item_id,
                            "item_name": result.get("item", {}).get("name", ""),
                            "container_id": request_container_id,
                            "zone": result.get("item", {}).get("zone", "")
                        })
                    
                    # Add to return items
                    return_items.append({
                        "item_id": item_id,
                        "name": item.get('name', ''),
                        "reason": item.get('reason', ''),
                        "container_id": request_container_id,
                        "position": item.get('position', ''),
                        "retrieval_steps": result.get("retrieval_steps", [])
                    })
        
        print(f"Generated {len(all_retrieval_steps)} retrieval steps")
        print(f"Return items: {return_items}")
        
        return ReturnPlanResponse(
            success=True,
            returnPlan=return_items,
            retrievalSteps=all_retrieval_steps,
            returnManifest=ReturnManifest(
                totalVolume=round(total_volume, 2),
                totalWeight=round(total_weight, 2),
                undockingContainerId=request.undockingContainerId,
                undockingDate=request.undockingDate
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
            returnPlan=[],
            retrievalSteps=[],
            returnManifest=ReturnManifest(
                undockingContainerId=request.undockingContainerId if request else None,
                undockingDate=request.undockingDate if request else None
            )
        )

@router.post("/complete-undocking")
async def complete_undocking(request: CompleteUndockingRequest):
    waste_file = "waste_items.csv"
    items_file = "imported_items.csv"
    items_count = 0
    
    if os.path.exists(waste_file):
        try:
            waste_items_df = pl.read_csv(waste_file)
            if not waste_items_df.is_empty():
                filtered_df = waste_items_df.filter(pl.col("container_id") == request.undocking_container_id)
                items_count = filtered_df.height
                updated_df = waste_items_df.filter(pl.col("container_id") != request.undocking_container_id)
                updated_df.write_csv(waste_file)
        except Exception as e:
            print(f"Error processing waste items: {str(e)}")
    
    if os.path.exists(items_file):
        try:
            items_df = pl.read_csv(items_file)
            if "usage_count" in items_df.columns and "usage_limit" in items_df.columns:
                expired_items = items_df.filter(
                    (pl.col("usage_count") >= pl.col("usage_limit")) & 
                    (pl.col("container_id") == request.undocking_container_id)
                )
                
                if not expired_items.is_empty():
                    new_waste_items = []
                    
                    for item in expired_items.to_dicts():
                        position_str = f"(0,0,0),(0,0,0)"
                        new_waste_item = {
                            "item_id": item["item_id"],
                            "name": item["name"] if "name" in item else f"Item {item['item_id']}",
                            "reason": "Usage limit reached",
                            "container_id": item["container_id"],
                            "position": position_str
                        }
                        new_waste_items.append(new_waste_item)
                    
                    new_waste_df = pl.DataFrame(new_waste_items)
                    
                    if os.path.exists(waste_file) and not pl.read_csv(waste_file).is_empty():
                        combined_df = pl.concat([pl.read_csv(waste_file), new_waste_df])
                        combined_df.write_csv(waste_file)
                    else:
                        new_waste_df.write_csv(waste_file)
                    
                    items_count += new_waste_df.height
                    
                    items_df = items_df.filter(
                        ~((pl.col("usage_count") >= pl.col("usage_limit")) & 
                          (pl.col("container_id") == request.undocking_container_id))
                    )
                    items_df.write_csv(items_file)
        
        except Exception as e:
            print(f"Error processing items at usage limit: {str(e)}")
    
    return {"success": True, "items_removed": items_count}