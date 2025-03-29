import os
import polars as pl
from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException
import json

router = APIRouter(
    prefix="/api/logs",
    tags=["Logs"]
)

LOG_FILE = "logs.csv"

# Load logs globally if CSV exists
logs_df = pl.DataFrame(schema={
    "timestamp": pl.Utf8,  # Initially as string; later converted to datetime
    "userId": pl.Utf8,
    "actionType": pl.Utf8,
    "itemId": pl.Utf8,
    "details": pl.Object  # Store as dictionary for structured logging
})


@router.get("/")
async def get_logs(
    startDate: str = Query(..., description="Start date in ISO format (YYYY-MM-DDTHH:MM:SSZ)"),
    endDate: str = Query(..., description="End date in ISO format (YYYY-MM-DDTHH:MM:SSZ)"),
    itemId: str = Query(None, description="Optional Item ID filter"),
    userId: str = Query(None, description="Optional User ID filter"),
    actionType: str = Query(None, description='Optional action type: "placement", "retrieval", "rearrangement", "disposal"')
):
    global logs_df

    # Load logs if available
    if os.path.exists(LOG_FILE):
        logs_df = pl.read_csv(LOG_FILE)

    # Convert timestamps
    start_date = datetime.fromisoformat(startDate).replace(tzinfo=timezone.utc)
    end_date = datetime.fromisoformat(endDate).replace(tzinfo=timezone.utc)

    if logs_df.height > 0:
        logs_df = logs_df.with_columns(pl.col("timestamp").str.strptime(pl.Datetime).dt.convert_time_zone("UTC"))

        # Apply filters
        filtered_logs = logs_df.filter(
            (pl.col("timestamp") >= start_date) & (pl.col("timestamp") <= end_date)
        )

        # Convert logs to dict and parse JSON details
        logs_list = filtered_logs.to_dicts()

        for log in logs_list:
            try:
                log["details"] = json.loads(log["details"])  # Convert JSON string back to dict
            except json.JSONDecodeError:
                log["details"] = {
                    "fromContainer": "",
                    "toContainer": "",
                    "reason": log["details"]
                }  # Handle old string-based logs

        return {"logs": logs_list}

    return {"logs": []}
