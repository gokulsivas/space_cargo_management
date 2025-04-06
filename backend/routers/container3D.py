from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json
import os

router = APIRouter()

class Position(BaseModel):
    startCoordinates: dict
    endCoordinates: dict

class ContainerItem(BaseModel):
    item_id: str
    position: Position

class Container3DResponse(BaseModel):
    dimensions: dict
    items: List[ContainerItem]

# Store the latest container data
latest_container_data = None

@router.post("/container3d/update")
async def update_container_data(placement_data: dict):
    try:
        global latest_container_data
        latest_container_data = process_placement_data(placement_data)
        return {"success": True, "message": "Container data updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/container3d/data")
async def get_container_data():
    if not latest_container_data:
        return {
            "dimensions": {
                "width": 0,
                "height": 0,
                "depth": 0
            },
            "items": []
        }
    return latest_container_data

def process_placement_data(placement_data: dict) -> dict:
    """
    Process placement data into a format suitable for 3D visualization
    """
    try:
        # Extract container dimensions from the first placement
        if not placement_data.get("placements"):
            raise ValueError("No placements found in data")

        # Get container dimensions from the first placement
        first_placement = placement_data["placements"][0]
        container_id = first_placement.get("container_id")
        
        # In a real implementation, you would fetch container dimensions from a database
        # For now, we'll use default dimensions
        dimensions = {
            "width": 10,  # Default width in cm
            "height": 10,  # Default height in cm
            "depth": 10   # Default depth in cm
        }

        # Process items
        items = []
        for placement in placement_data.get("placements", []):
            if not placement.get("position"):
                continue

            item = {
                "item_id": placement.get("item_id", ""),
                "position": {
                    "startCoordinates": {
                        "width_cm": placement["position"]["startCoordinates"].get("width_cm", 0),
                        "height_cm": placement["position"]["startCoordinates"].get("height_cm", 0),
                        "depth_cm": placement["position"]["startCoordinates"].get("depth_cm", 0)
                    },
                    "endCoordinates": {
                        "width_cm": placement["position"]["endCoordinates"].get("width_cm", 0),
                        "height_cm": placement["position"]["endCoordinates"].get("height_cm", 0),
                        "depth_cm": placement["position"]["endCoordinates"].get("depth_cm", 0)
                    }
                }
            }
            items.append(item)

        return {
            "dimensions": dimensions,
            "items": items
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing placement data: {str(e)}") 