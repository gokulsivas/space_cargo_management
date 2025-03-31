import json
import re
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Tuple
import csv
import polars as pl
from pydantic import BaseModel
from schemas import ReturnPlanStep, ReturnPlanRequest, CompleteUndockingRequest, Position, RetrievalStep, ReturnItem, ReturnManifest, ReturnPlanResponse, Object3D, Octree
import os

router = APIRouter(
    prefix="/api/waste",
    tags=["waste"],
)

def parse_position(position_str: str) -> dict:
    """
    Parse a position string formatted as:
    "(x,y,z),(x,y,z)"
    and return a dict with startCoordinates and endCoordinates.
    """
    # Use regex to extract the content inside each pair of parentheses
    pattern = r"\((.*?)\)"
    matches = re.findall(pattern, position_str)

    if len(matches) != 2:
        # Fallback default if the format is not as expected
        return {
            "startCoordinates": {"width": 0, "depth": 0, "height": 0},
            "endCoordinates": {"width": 0, "depth": 0, "height": 0}
        }

    try:
        # For each tuple string, split by comma and convert to float (or int)
        def parse_tuple(tuple_str: str) -> dict:
            values = [float(v) for v in tuple_str.split(",")]
            # Assuming the order is (width, depth, height)
            return {"width": values[0], "depth": values[1], "height": values[2]}

        start_coords = parse_tuple(matches[0])
        end_coords = parse_tuple(matches[1])
        
        return {
            "startCoordinates": start_coords,
            "endCoordinates": end_coords
        }
    except Exception as e:
        print(f"Error parsing position tuple: {str(e)}")
        return {
            "startCoordinates": {"width": 0, "depth": 0, "height": 0},
            "endCoordinates": {"width": 0, "depth": 0, "height": 0}
        }

@router.get("/identify")
async def identify_waste():
    waste_file = "waste_items.csv"
    
    if not os.path.exists(waste_file):
        return {"success": False, "wasteItems": []}
    
    try:
        waste_df = pl.read_csv(waste_file)
        
        if waste_df.is_empty():
            return {"success": False, "wasteItems": []}

        waste_items_raw = waste_df.to_dicts()
        waste_items = []

        for item in waste_items_raw:
            position_value = item.get("position", "")
            # Determine if it looks like a JSON string (starts with {) or our tuple style (starts with ()
            if isinstance(position_value, str):
                if position_value.strip().startswith("{"):
                    print("Detected JSON format")
                    # if it's JSON, attempt to load via json.loads
                    try:
                        print("Parsing JSON")
                        position_dict = json.loads(position_value)
                    except Exception as e:
                        print(f"JSON parsing error: {str(e)}")
                        position_dict = {
                            "startCoordinates": {"width": 0, "depth": 0, "height": 0},
                            "endCoordinates": {"width": 0, "depth": 0, "height": 0}
                        }
                elif position_value.strip().startswith("("):
                    print("Detected tuple-like format")
                    # Use our custom parser for tuple-like strings
                    position_dict = parse_position(position_value)
                else:
                    print("Position string not in recognized format")
                    position_dict = {
                        "startCoordinates": {"width": 0, "depth": 0, "height": 0},
                        "endCoordinates": {"width": 0, "depth": 0, "height": 0}
                    }
            else:
                print("Position value is not a string")
                position_dict = {
                    "startCoordinates": {"width": 0, "depth": 0, "height": 0},
                    "endCoordinates": {"width": 0, "depth": 0, "height": 0}
                }
            
            # Create Position model (for instance, if you have additional validations in it)
            position_model = Position(
                startCoordinates=position_dict.get("startCoordinates", {"width": 0, "depth": 0, "height": 0}),
                endCoordinates=position_dict.get("endCoordinates", {"width": 0, "depth": 0, "height": 0})
            )
            
            formatted_item = {
                "itemId": str(item.get("itemId", "")),
                "name": str(item.get("name", "")),
                "reason": str(item.get("reason", "")),
                "containerId": str(item.get("containerId", "")),
                "position": position_model.dict()
            }
            
            waste_items.append(formatted_item)
        
        return {"success": True, "wasteItems": waste_items}
    
    except Exception as e:
        print(f"Error in identify_waste endpoint: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {"success": False, "wasteItems": []}

def calculate_volume(obj):
    width = abs(obj.end["width"] - obj.start["width"])
    depth = abs(obj.end["depth"] - obj.start["depth"])
    height = abs(obj.end["height"] - obj.start["height"])
    return width * depth * height

def load_imported_items(filename):
    imported_items = {}
    if not os.path.exists(filename):
        return imported_items
    
    with open(filename, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            imported_items[row["itemId"]] = float(row.get("mass", 0))
    
    return imported_items

def read_waste_data(waste_filename, imported_filename):
    objects = []
    imported_items = load_imported_items(imported_filename)
    weights = {}

    if not os.path.exists(waste_filename):
        return objects
    
    with open(waste_filename, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            coordinates = parse_position(row.get("position", ""))
            item_id = row.get("itemId", "")
            weight = imported_items.get(item_id, 0)  # Store weight separately
            obj = Object3D(
                item_id,
                row.get("name", ""),
                row.get("containerId", ""),
                coordinates["startCoordinates"],
                coordinates["endCoordinates"]
            )
            objects.append(obj)
            weights[item_id] = weight  # Store weight in a dictionary

    return objects, weights


@router.post("/return-plan", response_model=ReturnPlanResponse)
async def generate_return_plan(request: ReturnPlanRequest):
    # Read all waste data
    waste_objects_all, weights = read_waste_data("waste_items.csv", "imported_items.csv")
    
    # Filter objects by the requested container ID
    waste_objects = [obj for obj in waste_objects_all if obj.containerId == request.undockingContainerId]
    
    return_plan = []
    retrieval_steps = []
    return_items = []
    total_volume = 0
    total_weight = 0
    step_counter = 1
    
    while waste_objects:
        front_obj = min(waste_objects, key=lambda obj: obj.front_z, default=None)
        front_weight = weights.get(front_obj.itemId, 0) if front_obj else 0  # Get weight from dictionary

        if front_obj and total_weight + front_weight <= request.maxWeight:
            retrieval_steps.append(RetrievalStep(step=step_counter, action="remove", itemId=front_obj.itemId, itemName=front_obj.name))
            return_plan.append(ReturnPlanStep(
                step=step_counter,
                itemId=front_obj.itemId,
                itemName=front_obj.name,
                fromContainer=request.undockingContainerId,
                toContainer=front_obj.containerId
            ))
            return_items.append(ReturnItem(itemId=front_obj.itemId, name=front_obj.name, reason="Out of use"))
            total_weight += front_weight
            total_volume += calculate_volume(front_obj)
            waste_objects.remove(front_obj)
            step_counter += 1
    
    manifest = ReturnManifest(
        undockingContainerId=request.undockingContainerId,
        undockingDate=request.undockingDate,
        returnItems=return_items,
        totalVolume=total_volume,
        totalWeight=total_weight
    )
    
    return ReturnPlanResponse(
        success=True,
        returnPlan=return_plan,
        retrievalSteps=retrieval_steps,
        returnManifest=manifest
    )


@router.post("/complete-undocking")
async def complete_undocking(request: CompleteUndockingRequest):
    waste_file = "waste_items.csv"
    items_file = "imported_items.csv"  # Assuming this is where you store item usage data
    
    # Count items to be removed
    items_count = 0
    
    # First, process existing waste items
    if os.path.exists(waste_file):
        try:
            waste_items_df = pl.read_csv(waste_file)
            if not waste_items_df.is_empty():
                # Filter items to count
                filtered_df = waste_items_df.filter(pl.col("containerId") == request.undockingContainerId)
                items_count = filtered_df.height
                
                # Update the waste_items.csv file by removing these items
                updated_df = waste_items_df.filter(pl.col("containerId") != request.undockingContainerId)
                waste_items_df = updated_df  # Keep the updated DataFrame for later use
                updated_df.write_csv(waste_file)
        except Exception as e:
            print(f"Error processing waste items: {str(e)}")
    
    # Now check for items that have reached their usage limit
    if os.path.exists(items_file):
        try:
            # Read the items file
            items_df = pl.read_csv(items_file)
            
            # Filter items that have reached their usage limit (assuming there's a column for this)
            # You'll need to adjust this based on your actual data structure
            if "usageCount" in items_df.columns and "usageLimit" in items_df.columns:
                expired_items = items_df.filter(
                    (pl.col("usageCount") >= pl.col("usageLimit")) & 
                    (pl.col("containerId") == request.undockingContainerId)
                )
                
                if not expired_items.is_empty():
                    # Convert expired items to waste items format
                    new_waste_items = []
                    
                    for item in expired_items.to_dicts():
                        # Create a position string if needed
                        position_str = f"(0,0,0),(0,0,0)"  # Default position
                        if "position" in item:
                            position_str = item["position"]
                        
                        new_waste_item = {
                            "itemId": item["itemId"],
                            "name": item["name"] if "name" in item else f"Item {item['itemId']}",
                            "reason": "Usage limit reached",
                            "containerId": item["containerId"],
                            "position": position_str
                        }
                        new_waste_items.append(new_waste_item)
                    
                    # Create a DataFrame from the new waste items
                    new_waste_df = pl.DataFrame(new_waste_items)
                    
                    # Append to the existing waste items file
                    if os.path.exists(waste_file) and not waste_items_df.is_empty():
                        combined_df = pl.concat([waste_items_df, new_waste_df])
                        combined_df.write_csv(waste_file)
                    else:
                        new_waste_df.write_csv(waste_file)
                    
                    # Add the count of new waste items
                    items_count += new_waste_df.height
                    
                    # Update the items file to mark these items as processed
                    # This depends on your business logic - you might want to remove them,
                    # or update a status field, or reset their usage count
                    items_df = items_df.filter(
                        ~((pl.col("usageCount") >= pl.col("usageLimit")) & 
                          (pl.col("containerId") == request.undockingContainerId))
                    )
                    items_df.write_csv(items_file)
        
        except Exception as e:
            print(f"Error processing items at usage limit: {str(e)}")
            import traceback
            print(traceback.format_exc())
    
    return {"success": True, "itemsRemoved": items_count}