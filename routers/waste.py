from fastapi import APIRouter, HTTPException
from typing import List, Dict
import polars as pl
from pydantic import BaseModel
from schemas import WasteItem, ReturnPlanRequest, CompleteUndockingRequest
import os

router = APIRouter(
    prefix="/api/waste",
    tags=["waste"],
)

# Empty waste items DataFrame
waste_items_df = pl.DataFrame({
    "itemId": [],
    "name": [],
    "reason": [],
    "containerId": [],
    "position": []
})

# Sample return plans storage
return_plans = []
completed_undocking = {}

# Identify Waste Items
@router.get("/identify")
async def identify_waste():
    waste_file = "waste_items.csv"
    
    # Check if waste file exists
    if not os.path.exists(waste_file):
        return {"success": False, "wasteItems": []}
    
    try:
        # Load waste items from CSV
        waste_df = pl.read_csv(waste_file)
        
        if waste_df.is_empty():
            return {"success": False, "wasteItems": []}
        
        # Convert to list of dictionaries
        waste_items_raw = waste_df.to_dicts()
        waste_items = []
        
        # Format each waste item according to the required response structure
        for item in waste_items_raw:
            # Parse the position string from CSV
            position_str = item.get("position", "{}")
            if isinstance(position_str, str):
                try:
                    import json
                    position_data = json.loads(position_str)
                except:
                    # If parsing fails, use default empty position
                    position_data = {
                        "startCoordinates": {"width": 0, "depth": 0, "height": 0},
                        "endCoordinates": {"width": 0, "depth": 0, "height": 0}
                    }
            else:
                # Use default if not a string
                position_data = {
                    "startCoordinates": {"width": 0, "depth": 0, "height": 0},
                    "endCoordinates": {"width": 0, "depth": 0, "height": 0}
                }
            
            # Create formatted waste item
            formatted_item = {
                "itemId": str(item.get("itemId", "")),
                "name": str(item.get("name", "")),
                "reason": str(item.get("reason", "")),
                "containerId": str(item.get("containerId", "")),
                "position": position_data
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
    global return_plans
    
    if waste_items_df.is_empty():
        raise HTTPException(status_code=404, detail="No waste items found.")
    
    return_items = waste_items_df.filter(waste_items_df["containerId"] == request.undockingContainerId).to_dicts()
    if not return_items:
        raise HTTPException(status_code=404, detail="No waste items in this container.")
    
    return_manifest = {
        "undockingContainerId": request.undockingContainerId,
        "undockingDate": request.undockingDate,
        "returnItems": [{"itemId": item["itemId"], "name": item["name"], "reason": item["reason"]} for item in return_items],
        "totalVolume": len(return_items) * 0.5,  # Example calculation
        "totalWeight": min(request.maxWeight, len(return_items) * 2)  # Example calculation
    }
    
    return_plan = [{"step": i+1, "itemId": item["itemId"], "itemName": item["name"],
                    "fromContainer": item["containerId"], "toContainer": "Return Zone"} for i, item in enumerate(return_items)]
        
    retrieval_steps = [{"step": i+1, "action": "remove", "itemId": item["itemId"], "itemName": item["name"]} for i, item in enumerate(return_items)]
    
    return_plans.append(return_manifest)
        
    return {
        "success": True,
        "returnPlan": return_plan,
        "retrievalSteps": retrieval_steps,
        "returnManifest": return_manifest
    }


@router.post("/complete-undocking")
async def complete_undocking(request: CompleteUndockingRequest):
    global completed_undocking
    
    if request.undockingContainerId not in [plan["undockingContainerId"] for plan in return_plans]:
        raise HTTPException(status_code=404, detail="Return plan not found for this container.")
    
    completed_undocking[request.undockingContainerId] = {
        "timestamp": request.timestamp,
        "itemsRemoved": len([item for item in waste_items_df.to_dicts() if item["containerId"] == request.undockingContainerId])
    }
    
    return {"success": True, "itemsRemoved": completed_undocking[request.undockingContainerId]["itemsRemoved"]}


@router.post("/return-plan")
async def generate_return_plan(request: ReturnPlanRequest):
    global return_plans

    if waste_items_df.is_empty():
        raise HTTPException(status_code=404, detail="No waste items found.")

    return_items = waste_items_df.filter(waste_items_df["containerId"] == request.undockingContainerId).to_dicts()
    if not return_items:
        raise HTTPException(status_code=404, detail="No waste items in this container.")

    return_manifest = {
        "undockingContainerId": request.undockingContainerId,
        "undockingDate": request.undockingDate,
        "returnItems": [{"itemId": item["itemId"], "name": item["name"], "reason": item["reason"]} for item in return_items],
        "totalVolume": len(return_items) * 0.5,  # Example calculation
        "totalWeight": min(request.maxWeight, len(return_items) * 2)  # Example calculation
    }

    return_plan = [{"step": i+1, "itemId": item["itemId"], "itemName": item["name"], 
                    "fromContainer": item["containerId"], "toContainer": "Return Zone"} for i, item in enumerate(return_items)]
    
    retrieval_steps = [{"step": i+1, "action": "remove", "itemId": item["itemId"], "itemName": item["name"]} for i, item in enumerate(return_items)]

    return_plans.append(return_manifest)
    
    return {
        "success": True,
        "returnPlan": return_plan,
        "retrievalSteps": retrieval_steps,
        "returnManifest": return_manifest
    }


@router.post("/complete-undocking")
async def complete_undocking(request: CompleteUndockingRequest):
    global completed_undocking

    if request.undockingContainerId not in [plan["undockingContainerId"] for plan in return_plans]:
        raise HTTPException(status_code=404, detail="Return plan not found for this container.")

    completed_undocking[request.undockingContainerId] = {
        "timestamp": request.timestamp,
        "itemsRemoved": len([item for item in waste_items_df.to_dicts() if item["containerId"] == request.undockingContainerId])
    }

    return {"success": True, "itemsRemoved": completed_undocking[request.undockingContainerId]["itemsRemoved"]}
