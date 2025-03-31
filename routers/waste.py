import json
import re
from fastapi import APIRouter, HTTPException
from typing import List, Dict
import polars as pl
from pydantic import BaseModel
from schemas import WasteItem, ReturnPlanRequest, CompleteUndockingRequest, Position
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
    # Use regex to extract numbers between the parentheses
    pattern = r"$([^)]+)$"
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
                    # if it's JSON, attempt to load via json.loads
                    try:
                        position_dict = json.loads(position_value)
                    except Exception as e:
                        print(f"JSON parsing error: {str(e)}")
                        position_dict = {
                            "startCoordinates": {"width": 0, "depth": 0, "height": 0},
                            "endCoordinates": {"width": 0, "depth": 0, "height": 0}
                        }
                elif position_value.strip().startswith("("):
                    # Use our custom parser for tuple-like strings
                    position_dict = parse_position(position_value)
                else:
                    print("Position string not in recognized format")
                    position_dict = {
                        "startCoordinates": {"width": 0, "depth": 0, "height": 0},
                        "endCoordinates": {"width": 0, "depth": 0, "height": 0}
                    }
            else:
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



@router.post("/return-plan")
async def generate_return_plan(request: ReturnPlanRequest):
    try:
        # Define file paths
        waste_file = "waste_items.csv"
        containers_file = "imported_containers.csv"
        
        # Check if waste file exists
        if not os.path.exists(waste_file) or not os.path.exists(containers_file):
            return {"success": False, "message": "Required files not found"}
        
        # Load waste items and containers
        waste_df = pl.read_csv(waste_file)
        containers_df = pl.read_csv(containers_file)
        
        if waste_df.is_empty():
            return {"success": False, "message": "No waste items found"}
        
        # Filter waste items for the specified container
        return_items = waste_df.filter(pl.col("containerId") == request.undockingContainerId).to_dicts()
        
        if not return_items:
            return {"success": False, "message": "No waste items in this container"}
        
        # Get container information
        container_info = containers_df.filter(pl.col("containerId") == request.undockingContainerId)
        if container_info.is_empty():
            # Use default values if container info not found
            container_volume = 0
            container_weight = 0
        else:
            # Calculate container metrics (example calculations)
            container_volume = float(container_info.select("volume")[0, 0]) if "volume" in container_info.columns else 0
            container_weight = float(container_info.select("weight")[0, 0]) if "weight" in container_info.columns else 0
        
        # Generate return manifest
        return_manifest = {
            "undockingContainerId": request.undockingContainerId,
            "undockingDate": request.undockingDate,
            "returnItems": [
                {
                    "itemId": item["itemId"],
                    "name": item["name"],
                    "reason": item["reason"]
                } for item in return_items
            ],
            "totalVolume": container_volume + (len(return_items) * 0.5),  # Example calculation
            "totalWeight": min(request.maxWeight, container_weight + (len(return_items) * 2))  # Respect maxWeight limit
        }
        
        # Create return plan steps
        return_plan = []
        for i, item in enumerate(return_items):
            step = {
                "step": i + 1,
                "itemId": item["itemId"],
                "itemName": item["name"],
                "fromContainer": item["containerId"],
                "toContainer": request.undockingContainerId  # Items go to the undocking container
            }
            return_plan.append(step)
        
        # Create retrieval steps (more detailed than the example)
        retrieval_steps = []
        step_counter = 1
        
        for item in return_items:
            # Step 1: Remove item from its current location
            retrieval_steps.append({
                "step": step_counter,
                "action": "remove",
                "itemId": item["itemId"],
                "itemName": item["name"]
            })
            step_counter += 1
            
            # Step 2: Set aside temporarily
            retrieval_steps.append({
                "step": step_counter,
                "action": "setAside",
                "itemId": item["itemId"],
                "itemName": item["name"]
            })
            step_counter += 1
            
            # Step 3: Retrieve for packaging
            retrieval_steps.append({
                "step": step_counter,
                "action": "retrieve",
                "itemId": item["itemId"],
                "itemName": item["name"]
            })
            step_counter += 1
        
        # Store the return plan for future reference (optional)
        store_return_plan(request.undockingContainerId, return_manifest, return_plan, retrieval_steps)
        
        return {
            "success": True,
            "returnPlan": return_plan,
            "retrievalSteps": retrieval_steps,
            "returnManifest": return_manifest
        }
        
    except Exception as e:
        print(f"Error in generate_return_plan endpoint: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {"success": False, "message": "An error occurred while generating the return plan"}


# Helper function to store return plans
def store_return_plan(container_id, return_manifest, return_plan, retrieval_steps):
    try:
        plan_file = "return_plans.csv"
        
        # Create a dictionary to represent the plan
        plan_entry = {
            "containerId": container_id,
            "undockingDate": return_manifest["undockingDate"],
            "planDetails": {
                "manifest": return_manifest,
                "plan": return_plan,
                "steps": retrieval_steps
            }
        }
        
        # Convert to JSON for storage
        import json
        plan_json = json.dumps(plan_entry)
        
        # Store in CSV
        if not os.path.exists(plan_file):
            # Create file with headers
            plans_df = pl.DataFrame({
                "containerId": [container_id],
                "undockingDate": [return_manifest["undockingDate"]],
                "planDetails": [plan_json]
            })
        else:
            # Read existing file
            try:
                plans_df = pl.read_csv(plan_file)
                
                # Check if plan for this container already exists
                existing_plan = plans_df.filter(pl.col("containerId") == container_id)
                
                if not existing_plan.is_empty():
                    # Update existing plan
                    plans_df = plans_df.with_columns(
                        pl.when(pl.col("containerId") == container_id)
                        .then(pl.lit(plan_json))
                        .otherwise(pl.col("planDetails"))
                        .alias("planDetails")
                    )
                    
                    plans_df = plans_df.with_columns(
                        pl.when(pl.col("containerId") == container_id)
                        .then(pl.lit(return_manifest["undockingDate"]))
                        .otherwise(pl.col("undockingDate"))
                        .alias("undockingDate")
                    )
                else:
                    # Add new plan
                    new_plan = pl.DataFrame({
                        "containerId": [container_id],
                        "undockingDate": [return_manifest["undockingDate"]],
                        "planDetails": [plan_json]
                    })
                    plans_df = pl.concat([plans_df, new_plan])
                    
            except Exception as e:
                # Create new file if reading fails
                plans_df = pl.DataFrame({
                    "containerId": [container_id],
                    "undockingDate": [return_manifest["undockingDate"]],
                    "planDetails": [plan_json]
                })
        
        # Save the plans
        plans_df.write_csv(plan_file)
        print(f"Stored return plan for container {container_id}")
        
    except Exception as e:
        print(f"Error storing return plan: {str(e)}")


@router.post("/complete-undocking")
async def complete_undocking(request: CompleteUndockingRequest):
    global completed_undocking
    waste_file = "waste_items.csv"
    """
    # Verify if the container exists in return plans
    if request.undockingContainerId not in [plan["undockingContainerId"] for plan in return_plans]:
        raise HTTPException(status_code=404, detail="Return plan not found for this container.")"""
    
    # Count items to be removed
    items_count = 0
    
    if os.path.exists(waste_file):
        try:
            waste_items_df = pl.read_csv(waste_file)
            if not waste_items_df.is_empty():
                # Filter items to count
                filtered_df = waste_items_df.filter(pl.col("containerId") == request.undockingContainerId)
                items_count = filtered_df.height
                
                # Update the waste_items.csv file by removing these items
                updated_df = waste_items_df.filter(pl.col("containerId") != request.undockingContainerId)
                updated_df.write_csv(waste_file)
        except Exception as e:
            print(f"Error processing waste items: {str(e)}")
    
    # Store undocking information
    completed_undocking[request.undockingContainerId] = {
        "timestamp": request.timestamp,
        "itemsRemoved": items_count
    }
    
    return {"success": True, "itemsRemoved": items_count}