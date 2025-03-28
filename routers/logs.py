from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
import polars as pl

# Router setup
router = APIRouter(
    prefix="/api/logs",
    tags=["logs"],
)

# In-memory log storage (use a database in production)
log_columns = ["timestamp", "userId", "actionType", "itemId", "details"]
logs_df = pl.DataFrame(schema={col: pl.Utf8 for col in log_columns})


@router.get("/")
async def get_logs(
    startDate: str = Query(..., description="Start date in ISO format (YYYY-MM-DDTHH:MM:SSZ)"),
    endDate: str = Query(..., description="End date in ISO format (YYYY-MM-DDTHH:MM:SSZ)"),
    itemId: str = Query(None, description="Optional Item ID filter"),
    userId: str = Query(None, description="Optional User ID filter"),
    actionType: str = Query(None, description='Optional action type: "placement", "retrieval", "rearrangement", "disposal"')
):
    global logs_df

    # Convert string dates to datetime
    try:
        start_date = datetime.fromisoformat(startDate)
        end_date = datetime.fromisoformat(endDate)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601 format.")

    # Convert logs_df timestamp column to datetime for filtering
    if logs_df.height > 0:
        logs_df = logs_df.with_columns(pl.col("timestamp").str.strptime(pl.Datetime))

        # Apply filters
        filtered_logs = logs_df.filter(
            (pl.col("timestamp") >= start_date) & (pl.col("timestamp") <= end_date)
        )

        if itemId:
            filtered_logs = filtered_logs.filter(pl.col("itemId") == itemId)
        if userId:
            filtered_logs = filtered_logs.filter(pl.col("userId") == userId)
        if actionType:
            filtered_logs = filtered_logs.filter(pl.col("actionType") == actionType)

        return {"logs": filtered_logs.to_dicts()}

    return {"logs": []}  # Return empty if no logs exist
