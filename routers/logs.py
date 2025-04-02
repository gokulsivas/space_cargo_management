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
    "user_id": pl.Utf8,
    "action_type": pl.Utf8,
    "item_id": pl.Int64,  # Will be null for system-level operations
    "details": pl.Utf8  # Store as JSON string, will be parsed to dict when serving
})

# Initialize logs from file if it exists
if os.path.exists(LOG_FILE):
    try:
        logs_df = pl.read_csv(LOG_FILE)
        
        # Ensure the item_id column is of consistent type (Int64)
        if "item_id" in logs_df.columns:
            # Convert empty strings to None/null
            logs_df = logs_df.with_columns(
                pl.when(pl.col("item_id") == "").then(None).otherwise(pl.col("item_id")).cast(pl.Int64, strict=False)
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
            if details and isinstance(details, dict) and "item_id" in details:
                try:
                    processed_item_id = int(details["item_id"])
                except (ValueError, TypeError):
                    processed_item_id = None
    
    # Create new log entry with proper null handling for item_id
    new_log = pl.DataFrame({
        "timestamp": [timestamp],
        "user_id": [user_id],
        "action_type": [action_type],
        "item_id": [processed_item_id],  # This will be None for system operations
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
    item_id: int = Query(None, description="Optional Item ID filter"),
    user_id: str = Query(None, description="Optional User ID filter"),
    action_type: str = Query(None, description='Optional action type: "placement", "retrieval", "rearrangement", "disposal"')
):
    global logs_df

    # Load logs if available
    if os.path.exists(LOG_FILE):
        try:
            logs_df = pl.read_csv(LOG_FILE)
            
            # Ensure the item_id column is of consistent type (Int64)
            if "item_id" in logs_df.columns:
                # Convert empty strings to null first, then cast to Int64
                logs_df = logs_df.with_columns(
                    pl.when(pl.col("item_id") == "").then(None).otherwise(pl.col("item_id")).cast(pl.Int64, strict=False)
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
            if item_id is not None:
                # Debug print to check item_id value
                print(f"Filtering by item_id: {item_id}, type: {type(item_id)}")
                
                # Use is_not_null() to exclude null values before comparison
                filter_conditions = filter_conditions & (
                    pl.col("item_id").is_not_null() & (pl.col("item_id") == item_id)
                )
            
            if user_id is not None and user_id != "":
                filter_conditions = filter_conditions & (pl.col("user_id") == user_id)
                
            if action_type is not None and action_type != "":
                filter_conditions = filter_conditions & (pl.col("action_type") == action_type)
            
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
                        "from_container": "",
                        "to_container": "",
                        "reason": str(log["details"])
                    }
                
                # Ensure item_id is properly typed
                if log["item_id"] == "" or log["item_id"] is None:
                    log["item_id"] = None
                else:
                    try:
                        log["item_id"] = int(log["item_id"])
                    except (ValueError, TypeError):
                        log["item_id"] = None

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
        
        # Ensure the item_id column is of consistent type (Int64)
        if "item_id" in logs_df.columns:
            # Convert empty strings to null first, then cast to Int64
            logs_df = logs_df.with_columns(
                pl.when(pl.col("item_id") == "").then(None).otherwise(pl.col("item_id")).cast(pl.Int64, strict=False)
            )
            
            # Save fixed data back to CSV with proper null values
            logs_df.write_csv(LOG_FILE, null_values="null")
            return True
    except Exception as e:
        print(f"Error fixing logs file: {str(e)}")
        return False