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

# Initialize logs dataframe with proper schema
logs_df = pl.DataFrame(schema={
    "timestamp": pl.Utf8,
    "user_id": pl.Utf8,
    "action_type": pl.Utf8,
    "item_id": pl.Int64,
    "details": pl.Utf8
})

# Create logs file if it doesn't exist
if not os.path.exists(LOG_FILE):
    # Create an empty DataFrame with the correct schema
    logs_df.write_csv(LOG_FILE)

def log_action(user_id: str, action_type: str, item_id: int = None, details: dict = None):
    """
    Log an action to the system log
    
    Parameters:
    - user_id: ID of the user performing the action
    - action_type: Type of action being performed
    - item_id: Optional ID of the item affected
    - details: Optional dictionary of additional details
    """
    global logs_df
    
    # Create timestamp in UTC
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Convert details to JSON string
    details_json = json.dumps(details) if details else "{}"
    
    # Create new log entry
    new_log = pl.DataFrame({
        "timestamp": [timestamp],
        "user_id": [str(user_id)],
        "action_type": [action_type],
        "item_id": [item_id],
        "details": [details_json]
    })
    
    # Append to existing logs
    logs_df = pl.concat([logs_df, new_log])
    
    # Save to CSV
    logs_df.write_csv(LOG_FILE)

@router.get("/")
async def get_logs(
    startDate: str = Query(..., description="Start date in ISO format (YYYY-MM-DDTHH:MM:SSZ)"),
    endDate: str = Query(..., description="End date in ISO format (YYYY-MM-DDTHH:MM:SSZ)"),
    item_id: int = Query(None, description="Optional Item ID filter"),
    user_id: str = Query(None, description="Optional User ID filter"),
    action_type: str = Query(None, description='Optional action type: "placement", "retrieval", "rearrangement", "disposal"')
):
    global logs_df
    
    try:
        # Load logs from file
        if os.path.exists(LOG_FILE):
            logs_df = pl.read_csv(LOG_FILE)
            
            # Convert timestamps
            start_date = datetime.fromisoformat(startDate).replace(tzinfo=timezone.utc)
            end_date = datetime.fromisoformat(endDate).replace(tzinfo=timezone.utc)
            
            # Convert timestamp strings to datetime objects
            logs_df = logs_df.with_columns(
                pl.col("timestamp").str.strptime(pl.Datetime).dt.convert_time_zone("UTC")
            )
            
            # Apply filters
            filter_conditions = (pl.col("timestamp") >= start_date) & (pl.col("timestamp") <= end_date)
            
            if item_id is not None:
                filter_conditions = filter_conditions & (pl.col("item_id") == item_id)
            
            if user_id is not None:
                filter_conditions = filter_conditions & (pl.col("user_id") == user_id)
            
            if action_type is not None:
                filter_conditions = filter_conditions & (pl.col("action_type") == action_type)
            
            # Apply filters
            filtered_logs = logs_df.filter(filter_conditions)
            
            # Convert to list of dictionaries
            logs_list = filtered_logs.to_dicts()
            
            # Parse JSON details
            for log in logs_list:
                try:
                    log["details"] = json.loads(log["details"])
                except:
                    log["details"] = {}
            
            return {"logs": logs_list}
        
        return {"logs": []}
        
    except Exception as e:
        print(f"Error processing logs: {str(e)}")
        return {"logs": []}

# Add some test logs when the module is imported
if not os.path.exists(LOG_FILE) or logs_df.height == 0:
    # Add some sample logs
    log_action("user1", "placement", 1, {"container": "A", "zone": "Crew Quarters"})
    log_action("user2", "retrieval", 2, {"container": "B", "zone": "Storage"})
    log_action("user3", "rearrangement", 3, {"from_container": "A", "to_container": "B"})