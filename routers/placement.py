from fastapi import APIRouter, HTTPException
from schemas import CargoPlacementSystem, PlacementRequest, PlacementResponse  # ✅ Import PlacementResponse
import polars as pl

# Create CargoPlacementSystem instance
cargo_system = CargoPlacementSystem()

router = APIRouter(
    prefix="/api/placement",
    tags=["placement"],
)

@router.post("/", response_model=PlacementResponse)
async def process_placement(request: PlacementRequest) -> PlacementResponse:
    if not request.items or not request.containers:
        raise HTTPException(status_code=400, detail="Items and containers must be provided.")

    # Add items and containers
    cargo_system.add_items([item.dict() for item in request.items])
    cargo_system.add_containers([container.dict() for container in request.containers])

    # Optimize placement
    placement_result = cargo_system.optimize_placement()

    # Debugging logs
    print("Placement Result:", placement_result)

    # Extract success value
    success = False
    if "success" in placement_result.columns and not placement_result["success"].is_empty():
        success = placement_result["success"].item(0)

    # Create a mapping from zone to containerId
    container_map = {container.zone.strip(): container.containerId for container in request.containers}
    
    # Convert placements DataFrame to list of ItemPlacement objects with the new coordinate format
    placements = []
    if "placements" in placement_result.columns and placement_result["placements"].item(0) is not None:
        placements_df = placement_result["placements"].item(0)
        if not placements_df.is_empty():
            for row in placements_df.iter_rows(named=True):
                # Get containerId from zone
                container_id = container_map.get(row["zone"], "unknown")
                
                # Create position dict with new coordinate format
                position = {
                    "startCoordinates": {
                        "width": float(row["start_x"]),
                        "depth": float(row["start_y"]),
                        "height": float(row["start_z"])
                    },
                    "endCoordinates": {
                        "width": float(row["end_x"]),
                        "depth": float(row["end_y"]),
                        "height": float(row["end_z"])
                    }
                }
                
                # Create ItemPlacement object and add to list
                placements.append({
                    "itemId": row["itemId"],
                    "containerId": container_id,
                    "position": position
                })

    # Convert rearrangements DataFrame to list of RearrangementStep objects with the new coordinate format
    rearrangements = []
    if "rearrangements" in placement_result.columns and placement_result["rearrangements"].item(0) is not None:
        rearrangements_df = placement_result["rearrangements"].item(0)
        if not rearrangements_df.is_empty():
            for row in rearrangements_df.iter_rows(named=True):
                # Create fromPosition dict with new coordinate format
                from_position = {
                    "startCoordinates": {
                        "width": float(row.get("from_start_x", 0)),
                        "depth": float(row.get("from_start_y", 0)),
                        "height": float(row.get("from_start_z", 0))
                    },
                    "endCoordinates": {
                        "width": float(row.get("from_end_x", 0)),
                        "depth": float(row.get("from_end_y", 0)),
                        "height": float(row.get("from_end_z", 0))
                    }
                }
                
                # Create toPosition dict with new coordinate format if it exists
                to_position = None
                if "to_start_x" in row:
                    to_position = {
                        "startCoordinates": {
                            "width": float(row["to_start_x"]),
                            "depth": float(row["to_start_y"]),
                            "height": float(row["to_start_z"])
                        },
                        "endCoordinates": {
                            "width": float(row["to_end_x"]),
                            "depth": float(row["to_end_y"]),
                            "height": float(row["to_end_z"])
                        }
                    }
                
                # Default to same container if not specified
                to_container = row.get("toContainer", row.get("fromContainer", ""))
                
                # Create RearrangementStep object and add to list
                rearrangements.append({
                    "step": row.get("step", 0),
                    "action": row.get("action", "move"),
                    "itemId": row["itemId"],
                    "fromContainer": row.get("fromContainer", ""),
                    "fromPosition": from_position,
                    "toContainer": to_container,
                    "toPosition": to_position
                })

    # Create and return the PlacementResponse
    return PlacementResponse(
        success=success,
        placements=placements,
        rearrangements=rearrangements
    )