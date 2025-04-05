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
    item_id: Optional[int] = None
    name: Optional[str] = None

class TimeSimulationRequest(BaseModel):
    numOfDays: Optional[int] = None
    toTimestamp: Optional[str] = None
    itemsToBeUsedPerDay: List[ItemUsage] = []

@router.post("/day")
async def simulate_day(request: TimeSimulationRequest):
    try:
        if not os.path.exists("imported_items.csv"):
            return {
                "success": False,
                "error": "Imported items data not found"
            }
        
        items_df = pl.read_csv("imported_items.csv")
        current_date = datetime.now()

        # Handle empty or invalid dates
        items_df = items_df.with_columns([
            pl.when(pl.col("expiry_date").is_null() | (pl.col("expiry_date") == ""))
            .then(None)
            .otherwise(pl.col("expiry_date"))
            .alias("expiry_date")
        ])

        # Calculate simulation duration
        if request.toTimestamp and request.toTimestamp.strip():
            try:
                target_date = datetime.fromisoformat(request.toTimestamp.rstrip('Z'))
                days_to_simulate = (target_date - current_date).days
            except ValueError:
                days_to_simulate = request.numOfDays if request.numOfDays else 1
                target_date = current_date + timedelta(days=days_to_simulate)
        else:
            days_to_simulate = request.numOfDays if request.numOfDays else 1
            target_date = current_date + timedelta(days=days_to_simulate)

        if days_to_simulate < 0:
            days_to_simulate = 1
            target_date = current_date + timedelta(days=1)

        items_used = []
        items_expired = []
        items_depleted_today = []

        # Process each day
        for day in range(days_to_simulate):
            current_date += timedelta(days=1)
            
            # Check expiry dates
            for item in items_df.to_dicts():
                if item["expiry_date"]:
                    try:
                        expiry_date = parse_expiry_date(item["expiry_date"])
                        if expiry_date.date() <= current_date.date():
                            items_expired.append({
                                "item_id": item["item_id"],
                                "name": item["name"]
                            })
                            items_df = items_df.filter(pl.col("item_id") != item["item_id"])
                            continue
                    except ValueError:
                        continue
            
            # Process daily item usage
            for item_usage in request.itemsToBeUsedPerDay:
                filter_expr = []
                if item_usage.item_id is not None:
                    filter_expr.append(pl.col("item_id") == item_usage.item_id)
                if item_usage.name and item_usage.name.strip():
                    filter_expr.append(pl.col("name") == item_usage.name)
                
                if not filter_expr:
                    continue
                
                matching_items = items_df.filter(pl.any_horizontal(filter_expr))
                
                for item in matching_items.to_dicts():
                    current_uses = int(item["usage_limit"])
                    new_uses = max(0, current_uses - 1)
                    
                    items_df = items_df.with_columns([
                        pl.when(pl.col("item_id") == item["item_id"])
                        .then(new_uses)
                        .otherwise(pl.col("usage_limit"))
                        .alias("usage_limit")
                    ])
                    
                    items_used.append({
                        "item_id": item["item_id"],
                        "name": item["name"],
                        "remainingUses": new_uses
                    })
                    
                    if current_uses > 0 and new_uses == 0:
                        items_depleted_today.append({
                            "item_id": item["item_id"],
                            "name": item["name"]
                        })

        # Save updated state
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
        return {
            "success": False,
            "error": str(e)
        }

def parse_expiry_date(date_str: str) -> datetime:
    """Parse date string in either YYYY-MM-DD or DD-MM-YY format."""
    try:
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            day, month, year = date_str.split('-')
            if len(year) == 2:
                year = f"20{year}"
            return datetime(int(year), int(month), int(day))
    except Exception:
        raise ValueError(f"Invalid date format: {date_str}")