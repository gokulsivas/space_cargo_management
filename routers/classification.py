from fastapi import APIRouter, HTTPException
from schemas import CargoPlacementSystem, ClassificationRequest, CargoClassificationSystem
import polars as pl

router = APIRouter(
    prefix="/classification",
    tags=["classification"],
)

cargo_system = CargoPlacementSystem()  # Reuse the cargo system
classification_system = CargoClassificationSystem()

# Placeholder for dynamic zone rule loading
def load_zone_rules() -> dict:
    """Fetch zone classification rules dynamically (e.g., from a database)."""
    # TODO: Replace with real DB/API call in future
    return {
        "food": "Food Storage",
        "medical": "Medical Supplies",
        "tools": "Tool Cabinet",
        "electronics": "Electronics Bay",
        "waste": "Waste Disposal",
        "default": "General Storage"
    }

def classify_item(item: dict, zone_rules: dict) -> dict:
    """Classifies a single item into its correct zone dynamically."""
    category = item.get("category", "default").lower()
    zone = zone_rules.get(category, zone_rules["default"])  # O(1) lookup

    return {
        "itemId": item["itemId"],
        "name": item["name"],
        "category": category,
        "zone": zone
    }

@router.post("/assign")
async def assign_items_to_zones(request: ClassificationRequest):
    """
    Classifies incoming items into predefined zones based on their category.
    Optimized for efficient classification.
    """
    if not request.items:
        raise HTTPException(status_code=400, detail="No items provided for classification.")

    # Load zone rules dynamically
    zone_rules = load_zone_rules()

    # Classify all items efficiently
    new_items = [classify_item(item, zone_rules) for item in request.items]

    # Convert new items to a Polars DataFrame
    new_items_df = pl.DataFrame(new_items)

    # Merge into classification system, avoiding duplicates
    if not classification_system.items_df.is_empty():
        # Remove old entries for the same itemId before appending new ones
        classification_system.items_df = (
            classification_system.items_df
            .filter(~pl.col("itemId").is_in(new_items_df["itemId"]))
            .vstack(new_items_df)  # Append new items
        )
    else:
        classification_system.items_df = new_items_df

    return {"success": True, "classifiedItems": new_items}

@router.get("/item/{item_id}")
async def get_item_classification(item_id: str):
    """
    Fetches the classification details of a specific item by its ID.
    """
    items_df = classification_system.items_df

    if items_df.is_empty():
        raise HTTPException(status_code=404, detail="No items have been classified yet.")

    item = items_df.filter(pl.col("itemId") == item_id).to_dicts()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found.")

    return {"item": item[0]}  # Return first match

@router.put("/update/{item_id}")
async def update_item_classification(item_id: str, updated_zone: str):
    """
    Updates the classification (zone) of a specific item.
    """
    if classification_system.items_df.is_empty():
        raise HTTPException(status_code=404, detail="No items have been classified yet.")

    # Check if the item exists
    if classification_system.items_df.filter(pl.col("itemId") == item_id).is_empty():
        raise HTTPException(status_code=404, detail="Item not found.")

    # Update the specific item’s zone
    classification_system.items_df = classification_system.items_df.with_columns(
        pl.when(pl.col("itemId") == item_id)
        .then(pl.lit(updated_zone))
        .otherwise(pl.col("zone"))
        .alias("zone")
    )

    return {"success": True, "message": f"Item {item_id} updated to zone {updated_zone}"}

@router.delete("/reset")
async def reset_all_classifications():
    """
    Clears all classified items from the system.
    This operation is efficient as it directly resets the DataFrame.
    """
    classification_system.items_df = pl.DataFrame(schema=["itemId", "name", "category", "zone"])  # Reset with schema
    
    return {"success": True, "message": "All classifications reset successfully."}

