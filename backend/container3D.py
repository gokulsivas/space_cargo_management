from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json

router = APIRouter()

class Position(BaseModel):
    startCoordinates: dict
    endCoordinates: dict

class ContainerItem(BaseModel):
    item_id: str
    name: str
    position: Position

class Container3DResponse(BaseModel):
    container_id: str
    dimensions: dict
    items: List[ContainerItem]

# Store the latest placement data
latest_placement_data = None

@router.post("/container3d/update")
async def update_container_3d(placement_data: dict):
    """
    Update the container 3D data with new placement information
    """
    global latest_placement_data
    try:
        # Validate and process the placement data
        processed_data = process_placement_data(placement_data)
        latest_placement_data = processed_data
        return {"message": "Container 3D data updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/container3d/data")
async def get_container_3d_data():
    """
    Get the current container 3D data
    """
    if latest_placement_data is None:
        raise HTTPException(status_code=404, detail="No container data available")
    return latest_placement_data

def process_placement_data(placement_data: dict) -> dict:
    """
    Process placement data into a format suitable for 3D visualization
    """
    try:
        # Extract container information
        container = {
            "container_id": placement_data.get("container_id", "default"),
            "dimensions": {
                "width": placement_data.get("width_cm", 0),
                "depth": placement_data.get("depth_cm", 0),
                "height": placement_data.get("height_cm", 0)
            },
            "items": []
        }

        # Process each item's placement
        for placement in placement_data.get("placements", []):
            item = {
                "item_id": placement.get("item_id", ""),
                "name": placement.get("name", ""),
                "position": {
                    "startCoordinates": {
                        "width_cm": placement.get("position", {}).get("startCoordinates", {}).get("width_cm", 0),
                        "depth_cm": placement.get("position", {}).get("startCoordinates", {}).get("depth_cm", 0),
                        "height_cm": placement.get("position", {}).get("startCoordinates", {}).get("height_cm", 0)
                    },
                    "endCoordinates": {
                        "width_cm": placement.get("position", {}).get("endCoordinates", {}).get("width_cm", 0),
                        "depth_cm": placement.get("position", {}).get("endCoordinates", {}).get("depth_cm", 0),
                        "height_cm": placement.get("position", {}).get("endCoordinates", {}).get("height_cm", 0)
                    }
                }
            }
            container["items"].append(item)

        return container
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing placement data: {str(e)}") 