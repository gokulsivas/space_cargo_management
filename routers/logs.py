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
    "itemId": pl.Int64,  # Will be null for system-level operations
    "details": pl.Utf8  # Store as JSON string, will be parsed to dict when serving
})

# Initialize logs from file if it exists
if os.path.exists(LOG_FILE):
    try:
        logs_df = pl.read_csv(LOG_FILE)
        
        # Ensure the itemId column is of consistent type (Int64)
        if "itemId" in logs_df.columns:
            # Convert empty strings to None/null
            logs_df = logs_df.with_columns(
                pl.when(pl.col("itemId") == "").then(None).otherwise(pl.col("itemId")).cast(pl.Int64, strict=False)
            )
    except Exception as e:
        print(f"Error loading or processing logs: {str(e)}")


def log_action(user_id, action_type, item_id=None, details=None):
    """
    Log an action to the system log
    
    Parameters:
    - user_id: ID of the user performing the action (string)
    - action_type: Type of action being performed (string)
    - item_id: Optional ID of the item affected (integer or None)
    - details: Optional dictionary of additional details
    """
    global logs_df
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Convert details dictionary to JSON string
    details_json = json.dumps(details or {})
    
    # Handle item_id properly - ensure it's an integer or None
    processed_item_id = None
    if item_id is not None and item_id != "":
        try:
            processed_item_id = int(item_id)
        except (ValueError, TypeError):
            # If direct conversion fails, try to extract from details
            if details and isinstance(details, dict) and "itemId" in details:
                try:
                    processed_item_id = int(details["itemId"])
                except (ValueError, TypeError):
                    processed_item_id = None
    
    # Create new log entry with proper null handling for itemId
    new_log = pl.DataFrame({
        "timestamp": [timestamp],
        "userId": [user_id],
        "actionType": [action_type],
        "itemId": [processed_item_id],  # This will be None for system operations
        "details": [details_json]
    })
    
    # Append to dataframe
    logs_df = pl.concat([logs_df, new_log])
    
    # Save to CSV with proper null representation
    # Use null_values parameter to ensure None values are written as null in CSV
    logs_df.write_csv(LOG_FILE, null_values="null")


@router.get("/")
async def get_logs(
    startDate: str = Query(..., description="Start date in ISO format (YYYY-MM-DDTHH:MM:SSZ)"),
    endDate: str = Query(..., description="End date in ISO format (YYYY-MM-DDTHH:MM:SSZ)"),
    itemId: int = Query(None, description="Optional Item ID filter"),
    userId: str = Query(None, description="Optional User ID filter"),
    actionType: str = Query(None, description='Optional action type: "placement", "retrieval", "rearrangement", "disposal"')
):
    global logs_df

    # Load logs if available
    if os.path.exists(LOG_FILE):
        try:
            logs_df = pl.read_csv(LOG_FILE)
            
            # Ensure the itemId column is of consistent type (Int64)
            if "itemId" in logs_df.columns:
                # Convert empty strings to null first, then cast to Int64
                logs_df = logs_df.with_columns(
                    pl.when(pl.col("itemId") == "").then(None).otherwise(pl.col("itemId")).cast(pl.Int64, strict=False)
                )
        except Exception as e:
            print(f"Error loading or processing logs: {str(e)}")
            # Return empty result if loading fails
            return {"logs": []}

    # Convert timestamps
    start_date = datetime.fromisoformat(startDate).replace(tzinfo=timezone.utc)
    end_date = datetime.fromisoformat(endDate).replace(tzinfo=timezone.utc)

    if logs_df.height > 0:
        try:
            # Convert timestamp strings to datetime objects
            logs_df = logs_df.with_columns(pl.col("timestamp").str.strptime(pl.Datetime).dt.convert_time_zone("UTC"))

            # Start with date range filter
            filter_conditions = (pl.col("timestamp") >= start_date) & (pl.col("timestamp") <= end_date)
            
            # Add optional filters if provided
            if itemId is not None:
                # Debug print to check itemId value
                print(f"Filtering by itemId: {itemId}, type: {type(itemId)}")
                
                # Use is_not_null() to exclude null values before comparison
                filter_conditions = filter_conditions & (
                    pl.col("itemId").is_not_null() & (pl.col("itemId") == itemId)
                )
            
            if userId is not None and userId != "":
                filter_conditions = filter_conditions & (pl.col("userId") == userId)
                
            if actionType is not None and actionType != "":
                filter_conditions = filter_conditions & (pl.col("actionType") == actionType)
            
            # Apply all filters
            filtered_logs = logs_df.filter(filter_conditions)
            
            # Debug print to check filtered results
            print(f"Filtered logs count: {filtered_logs.height}")

            # Convert logs to dict and parse JSON details
            logs_list = filtered_logs.to_dicts()

            for log in logs_list:
                try:
                    # Convert JSON string back to dict
                    log["details"] = json.loads(log["details"]) 
                except (json.JSONDecodeError, TypeError):
                    # Handle old string-based logs or None values
                    log["details"] = {
                        "fromContainer": "",
                        "toContainer": "",
                        "reason": str(log["details"])
                    }
                
                # Ensure itemId is properly typed
                if log["itemId"] == "" or log["itemId"] is None:
                    log["itemId"] = None
                else:
                    try:
                        log["itemId"] = int(log["itemId"])
                    except (ValueError, TypeError):
                        log["itemId"] = None

            return {"logs": logs_list}
        
        except Exception as e:
            print(f"Error processing logs: {str(e)}, type: {type(e)}")
            import traceback
            traceback.print_exc()
            # Return empty result if processing fails
            return {"logs": []}

    return {"logs": []}


# Utility function to fix existing logs file if needed
def fix_logs_file():
    """Fix type issues in the logs.csv file if it exists"""
    if not os.path.exists(LOG_FILE):
        return False
    
    try:
        logs_df = pl.read_csv(LOG_FILE)
        
        # Ensure the itemId column is of consistent type (Int64)
        if "itemId" in logs_df.columns:
            # Convert empty strings to null first, then cast to Int64
            logs_df = logs_df.with_columns(
                pl.when(pl.col("itemId") == "").then(None).otherwise(pl.col("itemId")).cast(pl.Int64, strict=False)
            )
            
            # Save fixed data back to CSV with proper null values
            logs_df.write_csv(LOG_FILE, null_values="null")
            return True
    except Exception as e:
        print(f"Error fixing logs file: {str(e)}")
        return False