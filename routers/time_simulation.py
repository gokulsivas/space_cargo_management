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
    item_id: Optional[int]
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
        print(f"Initial DataFrame columns: {items_df.columns}")
        print(f"Sample of expiry dates: {items_df.select('expiry_date').head(5)}")

        current_date = datetime.now()
        print(f"Current date: {current_date}")

        # Validate expiry dates in the DataFrame
        items_df = items_df.with_columns([
            pl.when(pl.col("expiry_date").is_null() | (pl.col("expiry_date") == ""))
            .then(None)
            .otherwise(pl.col("expiry_date"))
            .alias("expiry_date")
        ])

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
        for day in range(days_to_simulate):
            current_date += timedelta(days=1)
            #print(f"\nProcessing day {day + 1}, date: {current_date}")
            
            # Check for expired items first
            for item in items_df.to_dicts():
                if item["expiry_date"]:
                    try:
                        # Parse ISO format date (YYYY-MM-DD)
                        expiry_date = parse_expiry_date(item["expiry_date"])
                        #print(f"Checking item {item['item_id']} ({item['name']}) - Expiry: {expiry_date}, Current: {current_date}")
                        if expiry_date.date() <= current_date.date():
                            print(f"Item {item['item_id']} ({item['name']}) has expired!")
                            items_expired.append({
                                "item_id": item["item_id"],
                                "name": item["name"]
                            })
                            # Remove expired items from DataFrame
                            items_df = items_df.filter(pl.col("item_id") != item["item_id"])
                            continue  # Skip processing this item for usage
                    except ValueError as e:
                        print(f"Error parsing expiry date for item {item['item_id']}: {str(e)}")
                        continue
            
            # Process items to be used each day
            for item_usage in request.itemsToBeUsedPerDay:
                # Find matching item
                filter_expr = []
                if item_usage.item_id:
                    filter_expr.append(pl.col("item_id") == item_usage.item_id)
                if item_usage.name:
                    filter_expr.append(pl.col("name") == item_usage.name)
                
                if not filter_expr:
                    continue
                
                matching_items = items_df.filter(pl.any_horizontal(filter_expr))
                
                for item in matching_items.to_dicts():
                    current_uses = int(item["usage_limit"])
                    new_uses = max(0, current_uses - 1)
                    
                    # Update usage limit in DataFrame
                    items_df = items_df.with_columns([
                        pl.when(pl.col("item_id") == item["item_id"])
                        .then(new_uses)
                        .otherwise(pl.col("usage_limit"))
                        .alias("usage_limit")
                    ])
                    
                    # Track used items
                    items_used.append({
                        "item_id": item["item_id"],
                        "name": item["name"],
                        "remainingUses": new_uses
                    })
                    
                    # Check if item is depleted
                    if current_uses > 0 and new_uses == 0:
                        items_depleted_today.append({
                            "item_id": item["item_id"],
                            "name": item["name"]
                        })

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

def parse_expiry_date(date_str: str) -> datetime:
    """Parse date string in either YYYY-MM-DD or DD-MM-YY format to datetime object."""
    try:
        # Try parsing as YYYY-MM-DD first
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            # If that fails, try DD-MM-YY format
            day, month, year = date_str.split('-')
            # Convert 2-digit year to 4-digit year (assuming 20xx)
            if len(year) == 2:
                year = f"20{year}"
            # Create datetime object
            return datetime(int(year), int(month), int(day))
    except Exception as e:
        raise ValueError(f"Invalid date format: {date_str}")