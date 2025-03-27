from fastapi import APIRouter, HTTPException
from schemas import CargoPlacementSystem, PlacementRequest, ItemPlacement
import polars as pl

cargo_system = CargoPlacementSystem()   #object of CargoPlacementSystem class defined in schemas.py

router = APIRouter(
    prefix="/placement",
    tags=["placement"],
)

@router.post("/")
async def process_placement(request: PlacementRequest):
    # Add items and containers to the system
    cargo_system.add_items(request.items)
    cargo_system.add_containers(request.containers)
    
    # Optimize placement
    placement_result = cargo_system.optimize_placement()
    
    return placement_result

# GET endpoint to retrieve current system state
@router.get("/")
async def get_current_placement():
    return {
        "items": cargo_system.items_df.to_dicts(as_rows = True),
        "containers": cargo_system.containers_df.to_dicts(as_rows = True)
    }

@router.get("/{item_id}")
async def get_item_placement(item_id: str):
    item = cargo_system.items_df.filter(cargo_system.items_df["itemId"] == item_id)

    if item.is_empty():
        raise HTTPException(status_code=404, detail="Item not found")

    return item.to_dicts()[0]  # Convert the item row to a dictionary and return

@router.put("/{item_id}")
async def update_item_placement(item_id: str, updated_placement: ItemPlacement):
    # Check if the item exists
    if cargo_system.items_df.filter(pl.col("itemId") == item_id).is_empty():
        raise HTTPException(status_code=404, detail="Item not found")

    # Convert updated_placement to a Polars DataFrame (single-row DataFrame)
    updated_df = pl.DataFrame([updated_placement.model_dump()])

    # Remove old row and add the updated one
    cargo_system.items_df = (
        cargo_system.items_df
        .filter(pl.col("itemId") != item_id)  # Remove old entry
        .vstack(updated_df)  # Add updated row
    )

    return {"success": True, "message": "Item placement updated", "updated_item": updated_placement}


#removing an item from the system or moving it to the waste container
@router.delete("/{item_id}")
async def remove_item(item_id: str, move_to_waste: bool = False):
    # Check if the item exists
    existing_item = cargo_system.items_df.filter(pl.col("itemId") == item_id)

    if existing_item.is_empty():
        raise HTTPException(status_code=404, detail="Item not found")

    if move_to_waste:
        # Move item to waste container (change container ID) instead of re-adding it to the dataframe
        cargo_system.items_df = cargo_system.items_df.with_columns(
            pl.when(pl.col("itemId") == item_id)
            .then({"containerId": "wasteContainer"})  # Update container
            .otherwise(pl.all())
        )
        message = f"Item {item_id} moved to waste container"
    else:
        # Remove the item
        cargo_system.items_df = cargo_system.items_df.filter(pl.col("itemId") != item_id)
        message = f"Item {item_id} removed successfully"

    return {"success": True, "message": message}

@router.delete("/")
async def remove_all_placements():
    """
    Remove all items and containers from the placement system.
    """
    cargo_system.items_df = cargo_system.items_df.clear()  # Clear items
    cargo_system.containers_df = cargo_system.containers_df.clear()  # Clear containers

    return {"success": True, "message": "All placements removed successfully."}