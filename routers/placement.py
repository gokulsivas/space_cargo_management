from fastapi import APIRouter, HTTPException
from schemas import CargoPlacementSystem, PlacementRequest, PlacementResponse
from algos.placement_algo import AdvancedCargoPlacement
import polars as pl
from typing import List, Dict
import traceback

router = APIRouter(
    prefix="/api/placement",
    tags=["placement"],
)

@router.post("/", response_model=PlacementResponse)
async def process_placement(request: PlacementRequest) -> PlacementResponse:
    if not request.items or not request.containers:
        raise HTTPException(status_code=400, detail="Items and containers must be provided.")

    try:
        placements = []
        rearrangements = []

        # Process each container separately
        for container in request.containers:
            print(f"Processing container {container.container_id} in zone {container.zone}")
            
            # Initialize advanced placement algorithm for this container
            cargo_placer = AdvancedCargoPlacement({
                "width_cm": float(container.width_cm),
                "depth_cm": float(container.depth_cm),
                "height_cm": float(container.height_cm)
            })

            # Convert items to the required format
            container_items = []
            for item in request.items:
                if item.preferred_zone == container.zone:
                    container_items.append({
                        "item_id": str(item.item_id),  # Convert to string for consistency
                        "name": item.name,
                        "width_cm": float(item.width_cm),
                        "depth_cm": float(item.depth_cm),
                        "height_cm": float(item.height_cm),
                        "priority": int(item.priority),
                        "expiry_date": item.expiry_date if item.expiry_date else "",
                        "usage_limit": int(item.usage_limit),
                        "mass_kg": 0.0  # Default value if not provided
                    })

            print(f"Found {len(container_items)} items for zone {container.zone}")

            if not container_items:
                continue

            # Find optimal placement for items in this container
            placement_results = cargo_placer.find_optimal_placement(container_items)
            
            # Convert results to API format
            for placement in placement_results:
                placements.append({
                    "item_id": int(placement["item_id"]),  # Convert back to int
                    "container_id": container.container_id,
                    "zone": container.zone,
                    "position": {
                        "startCoordinates": placement["position"]["startCoordinates"],
                        "endCoordinates": placement["position"]["endCoordinates"]
                    }
                })

            print(f"Generated {len(placement_results)} placements for container {container.container_id}")

        success = len(placements) > 0
        print(f"Placement complete. Success: {success}, Total placements: {len(placements)}")

        return PlacementResponse(
            success=success,
            placements=placements,
            rearrangements=rearrangements
        )

    except Exception as e:
        print(f"Error in placement processing: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))