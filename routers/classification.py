from fastapi import APIRouter, HTTPException
from schemas import CargoPlacementSystem, ClassificationRequest, CargoClassificationSystem
import polars as pl

router = APIRouter(
    prefix="/classification",
    tags=["classification"],
)

cargo_system = CargoPlacementSystem()  # Reuse the cargo system
classification_system = CargoClassificationSystem()

# Load zone rules dynamically (e.g., from a database or file)
ZONE_RULES_DB = {
    "food": "Food Storage",
    "medical": "Medical Supplies",
    "tools": "Tool Cabinet",
    "electronics": "Electronics Bay",
    "waste": "Waste Disposal",
    "default": "General Storage"
}

def load_zone_rules():
    """Loads the latest zone rules dynamically (DB or file)"""
    return ZONE_RULES_DB  # TODO: Replace with a real DB fetch

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
    """
    if not request.items:
        raise HTTPException(status_code=400, detail="No items provided for classification.")

    # Load zone rules dynamically
    zone_rules = load_zone_rules()

    # Classify all items using vectorized operations
    classified_items = [classify_item(item, zone_rules) for item in request.items]

    # Convert to a Polars DataFrame for efficient storage
    cargo_system.items_df = pl.DataFrame(classified_items)

    return {"success": True, "classifiedItems": classified_items}

@router.get("/items")
async def get_items_by_zone():
    """
    Retrieve all classified items grouped by their zones.
    This function is optimized for handling hundreds of zones efficiently.
    """
    items_df = classification_system.items_df

    if items_df.is_empty():
        return {"message": "No items have been classified yet."}

    # Group items by zone dynamically
    grouped_items = (
        items_df.groupby("zone")
        .agg_list()
        .to_dicts()
    )

    return {"classified_items": grouped_items}

@router.delete("/reset")
async def reset_all_classifications():
    """
    Clears all classified items from the system.
    This operation is efficient as it directly resets the DataFrame.
    """
    classification_system.items_df = classification_system.items_df.clear() 
    
    return {"success": True, "message": "All classifications reset successfully."}