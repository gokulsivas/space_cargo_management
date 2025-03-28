from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
import polars as pl
from schemas import TimeSimulationRequest

router = APIRouter(
    prefix="/api/simulate",
    tags=["time_simulation"],
)

# Sample items DataFrame (temporary storage)
items_df = pl.DataFrame({
    "itemId": [],
    "name": [],
    "remainingUses": [],
    "expiryDate": []
})

# Global variable to track simulated date
current_date = datetime.now(timezone.utc)

@router.post("/day")
async def simulate_day(request: TimeSimulationRequest):
    global current_date, items_df

    # Determine the new date
    if request.toTimestamp:
        try:
            new_date = datetime.fromisoformat(request.toTimestamp)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid timestamp format.")
    elif request.numOfDays is not None:
        new_date = current_date + timedelta(days=request.numOfDays)
    else:
        raise HTTPException(status_code=400, detail="Provide either numOfDays or toTimestamp.")

    # Lists to store changes
    items_used = []
    items_expired = []
    items_depleted_today = []

    # Process items used per day
    for item_usage in request.itemsToBeUsedPerDay:
        item_id = item_usage.get("itemId")
        item_name = item_usage.get("name")

        # Find the item in the DataFrame
        filtered_items = items_df.filter(
            (items_df["itemId"] == item_id) | (items_df["name"] == item_name)
        )

        if not filtered_items.is_empty():
            for item in filtered_items.to_dicts():
                item["remainingUses"] -= 1  # Reduce remaining uses
                if item["remainingUses"] <= 0:
                    items_depleted_today.append({"itemId": item["itemId"], "name": item["name"]})
        
                items_used.append({"itemId": item["itemId"], "name": item["name"], "remainingUses": max(0, item["remainingUses"])})

    # Check for expired items
    expired_items = items_df.filter(pl.col("expiryDate") <= new_date.isoformat()).to_dicts()
    for item in expired_items:
        items_expired.append({"itemId": item["itemId"], "name": item["name"]})

    # Update current date
    current_date = new_date

    return {
        "success": True,
        "newDate": new_date.isoformat(),
        "changes": {
            "itemsUsed": items_used,
            "itemsExpired": items_expired,
            "itemsDepletedToday": items_depleted_today
        }
    }
