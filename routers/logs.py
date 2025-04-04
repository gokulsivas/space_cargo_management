from fastapi import APIRouter, HTTPException, Query, Depends
import polars as pl
import os
import re
from typing import Optional, List
from schemas import (
    Coordinates, 
    Position, 
    Item_for_search, 
    SearchResponse, 
    RetrievalStep,
    RetrieveItemRequest,  
    PlaceItemRequest,           
    PlaceItemResponse     
)
from datetime import datetime, timezone, timedelta
import csv
from algos.retrieve_algo import PriorityAStarRetrieval
from algos.search_algo import ItemSearchSystem
import numpy as np
import pandas as pd
import json

router = APIRouter(
    prefix="/api/logs",
    tags=["Logs"]
)

cargo_file = "cargo_arrangement.csv"
items_file = "imported_items.csv"
containers_file = "imported_containers.csv"

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
    
    # Load existing logs and append new log
    if os.path.exists(LOG_FILE):
        existing_logs = pl.read_csv(LOG_FILE)
        logs_df = pl.concat([existing_logs, new_log])
    else:
        logs_df = new_log
    
    # Save to CSV
    logs_df.write_csv(LOG_FILE)

@router.get("")
async def get_logs(
    startDate: str = Query(..., description="Start date in ISO format (YYYY-MM-DDTHH:MM:SSZ)"),
    endDate: str = Query(..., description="End date in ISO format (YYYY-MM-DDTHH:MM:SSZ)"),
    item_id: int = Query(None, description="Optional Item ID filter"),
    user_id: str = Query(None, description="Optional User ID filter"),
    action_type: str = Query(None, description='Optional action type: "placement", "retrieval", "rearrangement", "disposal"')
):
    global logs_df
    
    try:
        # Fix invalid ISO format by removing extra colon after T
        startDate = startDate.replace("T:", "T")
        endDate = endDate.replace("T:", "T")
        
        print(f"Getting logs with filters: startDate={startDate}, endDate={endDate}, item_id={item_id}, user_id={user_id}, action_type={action_type}")
        
        # Load logs from file
        if os.path.exists(LOG_FILE):
            print(f"Reading logs from {LOG_FILE}")
            logs_df = pl.read_csv(LOG_FILE)
            print(f"Total logs found: {len(logs_df)}")
            
            # Convert timestamps
            start_date = datetime.fromisoformat(startDate).replace(tzinfo=timezone.utc)
            end_date = datetime.fromisoformat(endDate).replace(tzinfo=timezone.utc)
            print(f"Date range: {start_date} to {end_date}")
            
            # Convert timestamp strings to datetime objects
            logs_df = logs_df.with_columns(
                pl.col("timestamp").str.strptime(pl.Datetime).dt.convert_time_zone("UTC")
            )
            
            # Ensure item_id column is of type Int64 and handle null values
            logs_df = logs_df.with_columns(
                pl.col("item_id").cast(pl.Int64, strict=False)
            )
            
            # Apply filters
            filter_conditions = (pl.col("timestamp") >= start_date) & (pl.col("timestamp") <= end_date)
            
            if item_id is not None:
                print(f"Filtering by item_id: {item_id}")
                # Convert item_id to Int64 for comparison
                filter_conditions = filter_conditions & (pl.col("item_id") == pl.lit(item_id, dtype=pl.Int64))
            
            if user_id is not None:
                print(f"Filtering by user_id: {user_id}")
                filter_conditions = filter_conditions & (pl.col("user_id") == user_id)
            
            if action_type is not None:
                print(f"Filtering by action_type: {action_type}")
                filter_conditions = filter_conditions & (pl.col("action_type") == action_type)
            
            # Apply filters
            filtered_logs = logs_df.filter(filter_conditions)
            print(f"Logs after filtering: {len(filtered_logs)}")
            
            # Convert to list of dictionaries
            logs_list = filtered_logs.to_dicts()
            
            # Parse JSON details
            for log in logs_list:
                try:
                    log["details"] = json.loads(log["details"])
                except:
                    log["details"] = {}
            
            return {"logs": logs_list}
        
        print(f"Log file {LOG_FILE} not found")
        return {"logs": []}
        
    except Exception as e:
        print(f"Error processing logs: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {"logs": []}

