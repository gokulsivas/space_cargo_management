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
        print(f"Processing placement request with {len(request.items)} items and {len(request.containers)} containers")
        placements = []
        rearrangements = []

        # Process each container separately
        for container in request.containers:
            print(f"Processing container {container.containerId} for zone {container.zone}")
            
            # Initialize advanced placement algorithm for this container
            cargo_placer = AdvancedCargoPlacement({
                "width": container.width,
                "depth": container.depth,
                "height": container.height
            })

            # Get items assigned to this container's zone
            container_items = [
                item.dict() 
                for item in request.items 
                if item.preferredZone == container.zone
            ]
            
            print(f"Found {len(container_items)} items for zone {container.zone}")

            if not container_items:
                continue

            # Find optimal placement for items in this container
            container_placements = cargo_placer.find_optimal_placement(container_items)
            print(f"Generated {len(container_placements)} placements for container {container.containerId}")

            # Add container ID to placements
            for placement in container_placements:
                placement["containerId"] = container.containerId
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