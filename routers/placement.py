from fastapi import APIRouter, HTTPException
from schemas import CargoPlacementSystem, PlacementRequest, PlacementResponse
from algos.placement_algo import AdvancedCargoPlacement
import polars as pl

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
            
            # Initialize advanced placement algorithm for this container
            cargo_placer = AdvancedCargoPlacement({
                "width_cm": container.width_cm,
                "depth_cm": container.depth_cm,
                "height_cm": container.height_cm
            })

            # Get items assigned to this container's zone
            container_items = [
                item.dict() 
                for item in request.items 
                if item.preferred_zone == container.zone
            ]
            
            print(f"Found {len(container_items)} items for zone {container.zone}")

            if not container_items:
                continue

            # Find optimal placement for items in this container
            container_placements = cargo_placer.find_optimal_placement(container_items)
            print(f"Generated {len(container_placements)} placements for container {container.container_id}")

            # Add container ID to placements
            for placement in container_placements:
                placement["container_id"] = container.container_id
                placements.append(placement)

        success = len(placements) > 0
        print(f"Placement complete. Success: {success}, Total placements: {len(placements)}")

        return PlacementResponse(
            success=success,
            placements=placements,
            rearrangements=rearrangements
        )

    except Exception as e:
        print(f"Error in placement processing: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))