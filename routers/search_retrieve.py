from fastapi import APIRouter, HTTPException, Query
import polars as pl
from datetime import datetime

# Assume CargoPlacementSystem manages the storage
from schemas import CargoPlacementSystem

# Create instance of CargoPlacementSystem
cargo_system = CargoPlacementSystem()

router = APIRouter(
    prefix="/api",
    tags=["search_retrieve"],
)

@router.get("/search")
async def search_item(
    itemId: str = Query(None), 
    itemName: str = Query(None),
    userId: str = Query(None)
):
    if not itemId and not itemName:
        raise HTTPException(status_code=400, detail="Either 'itemId' or 'itemName' must be provided.")

    # Filter items in the DataFrame
    if itemId:
        result_df = cargo_system.items_df.filter(pl.col("itemId") == itemId)
    else:
        result_df = cargo_system.items_df.filter(pl.col("name") == itemName)

    if result_df.is_empty():
        return {"success": True, "found": False, "item": None, "retrievalSteps": []}

    item_data = result_df.to_dicts()[0]  # Convert to dictionary for response

    # Generate retrieval steps (dummy logic)
    retrieval_steps = [
        {"step": 1, "action": "remove", "itemId": item_data["itemId"], "itemName": item_data["name"]},
        {"step": 2, "action": "retrieve", "itemId": item_data["itemId"], "itemName": item_data["name"]}
    ]

    return {
        "success": True,
        "found": True,
        "item": item_data,
        "retrievalSteps": retrieval_steps
    }


@router.post("/retrieve")
async def retrieve_item(itemId: str, userId: str, timestamp: str):
    # Check if the item exists
    result_df = cargo_system.items_df.filter(pl.col("itemId") == itemId)
    if result_df.is_empty():
        raise HTTPException(status_code=404, detail="Item not found.")

    # Update usage count (dummy logic, assuming we track it)
    cargo_system.items_df = cargo_system.items_df.with_columns(
        (pl.when(pl.col("itemId") == itemId)
         .then(pl.col("usageCount") + 1)
         .otherwise(pl.col("usageCount"))).alias("usageCount")
    )

    # Log the retrieval (for analytics)
    retrieval_log = pl.DataFrame([{"itemId": itemId, "userId": userId, "timestamp": timestamp}])

    return {"success": True}


@router.post("/place")
async def place_item(itemId: str, userId: str, timestamp: str, containerId: str, position: dict):
    # Check if the item exists
    result_df = cargo_system.items_df.filter(pl.col("itemId") == itemId)
    if result_df.is_empty():
        raise HTTPException(status_code=404, detail="Item not found.")

    # Update the item's position and container
    cargo_system.items_df = cargo_system.items_df.with_columns(
        (pl.when(pl.col("itemId") == itemId)
         .then(containerId)
         .otherwise(pl.col("containerId"))).alias("containerId"),
        (pl.when(pl.col("itemId") == itemId)
         .then(position)
         .otherwise(pl.col("position"))).alias("position")
    )

    return {"success": True}
