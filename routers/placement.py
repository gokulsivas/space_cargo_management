from fastapi import APIRouter, HTTPException
from schemas import CargoPlacementSystem, PlacementRequest
import polars as pl

# Create CargoPlacementSystem instance
cargo_system = CargoPlacementSystem()

router = APIRouter(
    prefix="/api/placement",
    tags=["placement"],
)

@router.post("/")
async def process_placement(request: PlacementRequest) -> dict:
    if not request.items or not request.containers:
        raise HTTPException(status_code=400, detail="Items and containers must be provided.")

    # Add items and containers to the system
    cargo_system.add_items(request.items)
    cargo_system.add_containers(request.containers)

    # Optimize placement using Octree
    placement_result_df = cargo_system.optimize_placement()

    # Convert DataFrame results to a dictionary
    placement_result = placement_result_df.to_dicts()[0]  # Convert first row (single record) to a dictionary

    if not placement_result["placements"] or placement_result["placements"] == []:
        raise HTTPException(status_code=422, detail="Could not place all items. Insufficient space or constraints.")

    return placement_result
