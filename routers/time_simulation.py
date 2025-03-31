from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional
import polars as pl
import os

router = APIRouter(
    prefix="/api/simulate",
    tags=["time_simulation"],
)

class ItemUsage(BaseModel):
    itemId: Optional[int]
    name: Optional[str]

class TimeSimulationRequest(BaseModel):
    numOfDays: Optional[int] = None
    toTimestamp: Optional[str] = None
    itemsToBeUsedPerDay: List[ItemUsage]

@router.post("/day")
async def simulate_day(request: TimeSimulationRequest):
    # Validate input
    if request.numOfDays is None and request.toTimestamp is None:
        raise HTTPException(status_code=400, detail="Either numOfDays or toTimestamp must be provided")

    try:
        # Read imported items CSV
        if not os.path.exists("imported_items.csv"):
            raise HTTPException(status_code=404, detail="Imported items data not found")
        
        items_df = pl.read_csv("imported_items.csv")
        current_date = datetime.now()

        # Calculate target date
        if request.toTimestamp:
            target_date = datetime.fromisoformat(request.toTimestamp.rstrip('Z'))
            days_to_simulate = (target_date - current_date).days
        else:
            days_to_simulate = request.numOfDays
            target_date = current_date + timedelta(days=days_to_simulate)

        if days_to_simulate < 0:
            raise HTTPException(status_code=400, detail="Cannot simulate negative days")

        # Initialize tracking lists
        items_used = []
        items_expired = []
        items_depleted_today = []

        # Process each day of simulation
        for _ in range(days_to_simulate):
            current_date += timedelta(days=1)
            
            # Process items to be used each day
            for item_usage in request.itemsToBeUsedPerDay:
                # Find matching item
                filter_expr = []
                if item_usage.itemId:
                    filter_expr.append(pl.col("itemId") == item_usage.itemId)
                if item_usage.name:
                    filter_expr.append(pl.col("name") == item_usage.name)
                
                if not filter_expr:
                    continue
                
                matching_items = items_df.filter(pl.any_horizontal(filter_expr))
                
                for item in matching_items.to_dicts():
                    current_uses = int(item["usageLimit"])
                    new_uses = max(0, current_uses - 1)
                    
                    # Update usage limit in DataFrame
                    items_df = items_df.with_columns([
                        pl.when(pl.col("itemId") == item["itemId"])
                        .then(new_uses)
                        .otherwise(pl.col("usageLimit"))
                        .alias("usageLimit")
                    ])
                    
                    # Track used items
                    items_used.append({
                        "itemId": item["itemId"],
                        "name": item["name"],
                        "remainingUses": new_uses
                    })
                    
                    # Check if item is depleted
                    if current_uses > 0 and new_uses == 0:
                        items_depleted_today.append({
                            "itemId": item["itemId"],
                            "name": item["name"]
                        })

            # Check for expired items
            for item in items_df.to_dicts():
                if item["expiryDate"]:
                    try:
                        # Parse ISO format date (YYYY-MM-DD)
                        expiry_date = datetime.fromisoformat(item["expiryDate"])
                        if expiry_date <= current_date:
                            items_expired.append({
                                "itemId": item["itemId"],
                                "name": item["name"]
                            })
                            # Remove expired items from DataFrame
                            items_df = items_df.filter(pl.col("itemId") != item["itemId"])
                    except ValueError as e:
                        print(f"Error parsing expiry date for item {item['itemId']}: {str(e)}")
                        continue

        # Save updated items back to CSV
        items_df.write_csv("temp_imported_items.csv")

        return {
            "success": True,
            "newDate": target_date.isoformat(),
            "changes": {
                "itemsUsed": items_used,
                "itemsExpired": items_expired,
                "itemsDepletedToday": items_depleted_today
            }
        }

    except Exception as e:
        print(f"Error in simulate_day endpoint: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))