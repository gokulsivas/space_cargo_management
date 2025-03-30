from fastapi import APIRouter, HTTPException, Query, Depends, Request, Body
import polars as pl
from typing import Optional, List, Dict, Any
import os
import traceback
import json

from schemas import CargoPlacementSystem

# Global cargo system instance
_cargo_system = None

# CSV Paths
ITEMS_CSV_PATH = "./test_data_items.csv"
CONTAINERS_CSV_PATH = "./test_data_containers.csv"

# Create default CSV structure
def ensure_csv_files_exist():
    # Create items CSV if it doesn't exist
    if not os.path.exists(ITEMS_CSV_PATH) or os.path.getsize(ITEMS_CSV_PATH) == 0:
        default_items = pl.DataFrame({
            "itemId": ["sample1"], 
            "itemName": ["Sample Item"],
            "preferredZone": ["A"], 
            "priority": [1],
            "width": [10],
            "height": [10],
            "depth": [10],
            "usageCount": [0]
        })
        default_items.write_csv(ITEMS_CSV_PATH)
    
    # Create containers CSV if it doesn't exist
    if not os.path.exists(CONTAINERS_CSV_PATH) or os.path.getsize(CONTAINERS_CSV_PATH) == 0:
        default_containers = pl.DataFrame({
            "zone": ["A"], 
            "width": [100], 
            "height": [100], 
            "depth": [100]
        })
        default_containers.write_csv(CONTAINERS_CSV_PATH)

# Singleton pattern for cargo system
def get_cargo_system():
    global _cargo_system
    if _cargo_system is None:
        try:
            # Ensure CSV files exist
            ensure_csv_files_exist()
            
            _cargo_system = CargoPlacementSystem()
            _cargo_system.load_from_csv(ITEMS_CSV_PATH, CONTAINERS_CSV_PATH)
        except Exception as e:
            _cargo_system = CargoPlacementSystem()
            _cargo_system.loading_log.append(f"Error initializing cargo system: {str(e)}")
            _cargo_system.loading_log.append(traceback.format_exc())
    return _cargo_system

router = APIRouter(
    prefix="/api", 
    tags=["search_retrieve"]
)

@router.get("/search")
async def search_item(
    request: Request,
    cargo_system: CargoPlacementSystem = Depends(get_cargo_system),
    itemId: Optional[str] = Query(None),
    itemName: Optional[str] = Query(None),
    debug: bool = Query(False)
):
    if debug:
        return {
            "success": True, 
            "debug_info": cargo_system.loading_log,
            "items_empty": cargo_system.items_df.is_empty(),
            "items_count": len(cargo_system.items_df) if not cargo_system.items_df.is_empty() else 0,
            "containers_empty": cargo_system.containers_df.is_empty(),
            "containers_count": len(cargo_system.containers_df) if not cargo_system.containers_df.is_empty() else 0
        }

    if cargo_system.items_df.is_empty():
        ensure_csv_files_exist()
        cargo_system.load_from_csv(ITEMS_CSV_PATH, CONTAINERS_CSV_PATH)
        if cargo_system.items_df.is_empty():
            raise HTTPException(status_code=500, detail="Data not loaded properly.")

    if not itemId and not itemName:
        raise HTTPException(status_code=400, detail="Provide 'itemId' or 'itemName'.")

    # Search logic
    if itemId:
        result_df = cargo_system.items_df.filter(pl.col("itemId") == itemId)
    else:
        result_df = cargo_system.items_df.filter(pl.col("itemName").str.contains(itemName, ignore_case=True))

    if result_df.is_empty():
        return {"success": True, "found": False, "item": None, "retrievalSteps": []}

    # Extract first match
    item_data = result_df.row(0, named=True)

    # Ensure required fields exist in the dataset
    containerId = item_data.get("containerId", "unknown")
    zone = item_data.get("preferredZone", "unknown")
    position = item_data.get("position", None)

    # Convert position from string (if stored as such) to dict
    if isinstance(position, str):
        try:
            position = json.loads(position)
        except json.JSONDecodeError:
            position = None

    return {
        "success": True,
        "found": True,
        "item": {
            "itemId": item_data["itemId"],
            "name": item_data["itemName"],
            "containerId": containerId,
            "zone": zone,
            "position": position or {
                "startCoordinates": {"width": 0, "depth": 0, "height": 0},
                "endCoordinates": {"width": 0, "depth": 0, "height": 0}
            }
        },
        "retrievalSteps": []
    }


@router.post("/retrieve")
async def retrieve_item(
    itemId: str, 
    userId: str, 
    timestamp: str,
    cargo_system: CargoPlacementSystem = Depends(get_cargo_system)
):
    result_df = cargo_system.items_df.filter(pl.col("itemId") == itemId)
    if result_df.is_empty():
        raise HTTPException(status_code=404, detail="Item not found.")

    if "usageCount" not in cargo_system.items_df.columns:
        cargo_system.items_df = cargo_system.items_df.with_columns(pl.lit(0).alias("usageCount"))

    cargo_system.items_df = cargo_system.items_df.with_columns(
        (pl.when(pl.col("itemId") == itemId).then(pl.col("usageCount") + 1).otherwise(pl.col("usageCount"))).alias("usageCount")
    )

    cargo_system.items_df.write_csv(ITEMS_CSV_PATH)

    return {"success": True}

@router.post("/place")
async def place_item(
    itemId: str, 
    userId: str, 
    timestamp: str, 
    containerId: str, 
    position: dict,
    cargo_system: CargoPlacementSystem = Depends(get_cargo_system)
):
    result_df = cargo_system.items_df.filter(pl.col("itemId") == itemId)
    if result_df.is_empty():
        raise HTTPException(status_code=404, detail="Item not found.")

    if "containerId" not in cargo_system.items_df.columns:
        cargo_system.items_df = cargo_system.items_df.with_columns(pl.lit("unknown").alias("containerId"))

    if "position" not in cargo_system.items_df.columns:
        cargo_system.items_df = cargo_system.items_df.with_columns(pl.lit(None).alias("position"))

    cargo_system.items_df = cargo_system.items_df.with_columns(
        (pl.when(pl.col("itemId") == itemId).then(containerId).otherwise(pl.col("containerId"))).alias("containerId"),
        (pl.when(pl.col("itemId") == itemId).then(str(position)).otherwise(pl.col("position"))).alias("position")
    )

    cargo_system.items_df.write_csv(ITEMS_CSV_PATH)

    return {"success": True}