from fastapi import APIRouter, HTTPException, Request
from schemas import (
    CargoPlacementSystem, 
    PlacementRequest, 
    PlacementResponse,
    Item_for_search,
    Position,
    Coordinates
)
from algos.placement_algo import AdvancedCargoPlacement
import polars as pl
from typing import List, Dict, Any
from pydantic import BaseModel

router = APIRouter(
    prefix="/api/placement",
    tags=["placement"],
)

class Item(BaseModel):
    item_id: int
    name: str
    width_cm: float
    depth_cm: float
    height_cm: float
    mass_kg: float = 0.0  # Making mass_kg optional with default value
    priority: int
    expiry_date: str
    usage_limit: int
    preferred_zone: str
    
    

class Container(BaseModel):
    container_id: str
    zone: str
    width_cm: float
    depth_cm: float
    height_cm: float

class PlacementInput(BaseModel):
    items: List[Item]
    containers: List[Container]

def transform_input(input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transform input data to match the expected format for placement algorithm."""
    transformed_items = []
    for item in input_data["items"]:
        # Create Coordinates for start and end positions
        start_coords = {
            "width_cm": 0,  # Initial position
            "depth_cm": 0,
            "height_cm": 0
        }
        end_coords = {
            "width_cm": item["width_cm"],
            "depth_cm": item["depth_cm"],
            "height_cm": item["height_cm"]
        }
        
        # Create Position
        position = {
            "startCoordinates": start_coords,
            "endCoordinates": end_coords
        }
        
        # Create transformed item
        transformed_item = {
            "item_id": item["item_id"],
            "name": item["name"],
            "width_cm": item["width_cm"],
            "depth_cm": item["depth_cm"],
            "height_cm": item["height_cm"],
            "mass_kg": item.get("mass_kg", 0),  # Default to 0 if not provided
            "priority": item["priority"],
            "expiry_date": item.get("expiry_date", ""),
            "usage_limit": item.get("usage_limit", 0),
            "preferred_zone": item["preferred_zone"],
            "position": position
        }
        transformed_items.append(transformed_item)
    
    return transformed_items

@router.post("/", response_model=PlacementResponse)
async def process_placement(input_data: PlacementInput) -> PlacementResponse:
    transformed_items = transform_input(input_data.dict())
    try:
        # Transform input data
        transformed_items = transform_input(input_data.dict())
        print("once")

        placements = []
        all_rearrangements = []

        # Process each container separately
        for container in input_data.containers:
            
            print(f"Processing container {container.container_id} for zone {container.zone}")
            
            # Initialize advanced placement algorithm for this container
            cargo_placer = AdvancedCargoPlacement({
                "width_cm": container.width_cm,
                "depth_cm": container.depth_cm,
                "height_cm": container.height_cm
            })

            # Get items assigned to this container's zone
            container_items = [
                item for item in transformed_items 
                if item["preferred_zone"] == container.zone
            ]
            
            print(f"Found {len(container_items)} items for zone {container.zone}")

            if not container_items:
                continue

            # Find optimal placement for items in this container
            container_placements, container_rearrangements = cargo_placer.find_optimal_placement(container_items)
            print(f"Generated {len(container_placements)} placements and {len(container_rearrangements)} rearrangements for container {container.container_id}")

            # Add container ID to placements and rearrangements
            for placement in container_placements:
                placement["container_id"] = container.container_id
                placements.append(placement)
                
            for rearrangement in container_rearrangements:
                rearrangement["container_id"] = container.container_id
                all_rearrangements.append(rearrangement)

        success = len(placements) > 0
        print(f"Placement complete. Success: {success}, Total placements: {len(placements)}, Total rearrangements: {len(all_rearrangements)}")

        return PlacementResponse(
            success=success,
            placements=placements,
            rearrangements=all_rearrangements
        )

    except Exception as e:
        print(f"Error in placement processing: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))