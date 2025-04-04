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
    # Create timestamp in UTC
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"Logging action: user_id={user_id}, action_type={action_type}, item_id={item_id}")
    
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
        print(f"Reading existing logs from {LOG_FILE}")
        existing_logs = pl.read_csv(LOG_FILE)
        logs_df = pl.concat([existing_logs, new_log])
    else:
        print(f"Creating new logs file at {LOG_FILE}")
        logs_df = new_log
    
    # Save to CSV
    print(f"Saving logs to {LOG_FILE}")
    logs_df.write_csv(LOG_FILE)
    print(f"Current logs count: {len(logs_df)}")

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

# Add some test logs with specific timestamps and item_id
test_timestamp = "2025-04-04T00:00:00Z"  # Using a date within the requested range

# Add test logs with various item_ids
log_action("user1", "placement", 123, {"container": "A", "zone": "Crew Quarters"})
log_action("user2", "retrieval", 123, {"container": "B", "zone": "Storage"})
log_action("user3", "rearrangement", 123, {"from_container": "A", "to_container": "B"})
log_action("user4", "placement", 1, {"container": "C", "zone": "Lab"})
log_action("user5", "retrieval", 2, {"container": "D", "zone": "Storage"})
log_action("user6", "rearrangement", 3, {"from_container": "C", "to_container": "D"})

@router.get("/search", response_model=SearchResponse)
async def search_item(
    item_id: Optional[int] = Query(None),
    name: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None, description="Optional user ID for logging purposes")
):
    try:
        # Load and validate required files
        if not all(os.path.exists(file) for file in [items_file, containers_file, cargo_file]):
            print(f"Missing required files. Checking: {items_file}, {containers_file}, {cargo_file}")
            return SearchResponse(success=False, found=False)

        # Load all required data
        items_df = pl.read_csv(items_file)
        containers_df = pl.read_csv(containers_file)
        cargo_df = pl.read_csv(cargo_file)

        if items_df.is_empty() or containers_df.is_empty() or cargo_df.is_empty():
            print("One or more data files are empty")
            return SearchResponse(success=False, found=False)

        # Convert DataFrames to list of dicts
        items_data = items_df.to_dicts()
        containers_data = containers_df.to_dicts()
        cargo_data = cargo_df.to_dicts()
        
        # Initialize search system
        search_system = ItemSearchSystem(
            items_data=items_data,
            containers_data=containers_data,
            cargo_data=cargo_data
        )
        
        # Perform search based on input
        if item_id is not None:
            print(f"Searching for item_id: {item_id}")
            result = search_system.search_by_id(item_id)
        elif name is not None:
            print(f"Searching for name: {name}")
            result = search_system.search_by_name(name)
        else:
            raise HTTPException(status_code=400, detail="Either item_id or name must be provided")

        # Handle search results
        if not result["success"]:
            print(f"Search unsuccessful: {result.get('message', 'Unknown error')}")
            return SearchResponse(success=False, found=False)
            
        if not result["found"]:
            print(f"Item not found: {result.get('message', 'Unknown reason')}")
            return SearchResponse(success=True, found=False)
            
        # Convert successful result to SearchResponse format
        try:
            print(f"Item found: {result['item']}")
            
            # Create the response
            response = SearchResponse(
                success=True,
                found=True,
                item=Item_for_search(
                    item_id=result["item"]["item_id"],
                    name=result["item"]["name"],
                    container_id=result["item"]["container_id"],
                    zone=result["item"]["zone"],
                    position=Position(
                        startCoordinates=Coordinates(**result["item"]["position"]["startCoordinates"]),
                        endCoordinates=Coordinates(**result["item"]["position"]["endCoordinates"])
                    )
                ),
                retrieval_steps=[
                    RetrievalStep(
                        step=step["step"],
                        action=step["action"],
                        item_id=step["item_id"],
                        item_name=step["item_name"]
                    ) for step in result.get("retrieval_steps", [])
                ]
            )
            
            # Log the search if user_id is provided
            if user_id:
                log_action(
                    user_id=user_id,
                    action_type="search",
                    item_id=result["item"]["item_id"],
                    details={"search_type": "id" if item_id else "name", "query": item_id or name}
                )
                
            return response
            
        except Exception as e:
            print(f"Error formatting response: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return SearchResponse(success=False, found=False)
            
    except Exception as e:
        print(f"Error in search endpoint: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return SearchResponse(success=False, found=False)

@router.post("/retrieve")
async def retrieve_item(request: RetrieveItemRequest):
    try:
        item_id = request.item_id
        user_id = request.user_id
        timestamp = request.timestamp

        if not timestamp:
            timestamp = datetime.datetime.now().isoformat()

        items_file = "imported_items.csv"    
        containers_file = "imported_containers.csv"
        cargo_file = "cargo_arrangement.csv"
        waste_file = "waste_items.csv"

        if not all(os.path.exists(file) for file in [items_file, cargo_file, containers_file]):
            return {"success": False}

        items_df = pl.read_csv(items_file)
        cargo_df = pl.read_csv(cargo_file)
        containers_df = pl.read_csv(containers_file)

        item_in_cargo = cargo_df.filter(pl.col("item_id") == item_id)
        if item_in_cargo.is_empty():
            return {"success": False}

        item_data = items_df.filter(pl.col("item_id") == item_id)
        if item_data.is_empty():
            return {"success": False}

        zone = item_in_cargo.select("zone")[0, 0]
        container_data = containers_df.filter(pl.col("zone") == zone)
        if container_data.is_empty():
            return {"success": False, "error": "Container not found"}

        container_dims = container_data.row(0, named=True)
        retriever = PriorityAStarRetrieval({
            "width_cm": float(container_dims["width_cm"]),
            "depth_cm": float(container_dims["depth_cm"]),
            "height_cm": float(container_dims["height_cm"])
        })

        coord_str = item_in_cargo.select("coordinates")[0, 0]
        coords = re.findall(r'[-+]?\d*\.\d+|[-+]?\d+', coord_str)
        if len(coords) < 6:
            return {"success": False, "error": "Invalid coordinates"}

        start_pos = (0, 0, 0)
        target_pos = (int(float(coords[0])), int(float(coords[1])), int(float(coords[2])))

        blocking_items = cargo_df.filter(
            (pl.col("zone") == zone) & 
            (pl.col("item_id") != item_id)
        )

        for blocking_item in blocking_items.iter_rows(named=True):
            block_coords = re.findall(r'[-+]?\d*\.\d+|[-+]?\d+', blocking_item["coordinates"])
            if len(block_coords) >= 6:
                x1, y1, z1 = map(lambda x: int(float(x)), block_coords[:3])
                x2, y2, z2 = map(lambda x: int(float(x)), block_coords[3:6])
                for x in range(x1, x2+1):
                    for y in range(y1, y2+1):
                        for z in range(z1, z2+1):
                            retriever.occupied_spaces.add((x, y, z))

        path = retriever.find_retrieval_path(start_pos, target_pos, str(item_id))
        if not path:
            return {"success": False, "error": "No valid retrieval path found"}

        retrieval_steps = []
        for idx, step in enumerate(path.steps, 1):
            retrieval_steps.append({
                "step": idx,
                "action": "move",
                "item_id": item_id,
                "from": {
                    "x": step["from"][0],
                    "y": step["from"][1],
                    "z": step["from"][2]
                },
                "to": {
                    "x": step["to"][0],
                    "y": step["to"][1],
                    "z": step["to"][2]
                },
                "priority": step["priority"]
            })

        current_usage = int(items_df.filter(pl.col("item_id") == item_id).select("usage_limit")[0, 0])
        if current_usage <= 0:
            return {"success": False, "error": "Item has no uses left"}

        new_usage = current_usage - 1
        print(f"New usage limit for item {item_id}: {new_usage}")

        updated_items_df = items_df.with_columns(
            pl.when(pl.col("item_id") == item_id)
            .then(pl.lit(new_usage))
            .otherwise(pl.col("usage_limit"))
            .alias("usage_limit")
        )

        updated_items_df.write_csv(items_file)
        log_retrieval(item_id, user_id, timestamp)

        if new_usage == 0:
            print(f"Removing item {item_id} from cargo as it has 0 uses left")
            updated_cargo_df = cargo_df.filter(pl.col("item_id") != item_id)
            updated_cargo_df.write_csv(cargo_file)

            zone = item_in_cargo.select("zone")[0, 0]
            container_id_df = containers_df.filter(pl.col("zone") == zone)
            if container_id_df.is_empty():
                print("Error: No container found for the given zone.")
                if new_usage == 0 and (item_id not in cargo_df["item_id"].to_list()):
                    return {"success": False}

            container_id = container_id_df.select("container_id")[0, 0]
            position_data = item_in_cargo.select("coordinates")[0, 0]

            add_to_waste_items(
                item_id=item_id,
                name=item_data.select("name")[0, 0],
                reason="Out of Uses",
                container_id=container_id,
                position=position_data
            )

        return {"success": True}

    except Exception as e:
        print(f"Error in retrieve endpoint: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {"success": False}

def add_to_waste_items(item_id, name, reason, container_id, position):
    waste_file = "waste_items.csv"
    new_waste_item = pl.DataFrame({
        "item_id": [int(item_id)],
        "name": [name],
        "reason": [reason],
        "container_id": [str(container_id)],
        "position": [str(position)]
    })

    if not os.path.exists(waste_file):
        print(f"Creating new waste_items.csv file with item {item_id}")
        new_waste_item.write_csv(waste_file)
    else:
        try:
            waste_df = pl.read_csv(waste_file)
            print(f"Appending item {item_id} to existing waste_items.csv")
            updated_waste_df = pl.concat([waste_df, new_waste_item])
            updated_waste_df.write_csv(waste_file)
        except Exception as e:
            print(f"Error appending to waste_items.csv: {str(e)}")
            print(f"Creating new waste_items.csv file with item {item_id}")
            new_waste_item.write_csv(waste_file)

    print(f"Added item {item_id} to waste items with reason: {reason}")

def log_retrieval(item_id, user_id, timestamp):
    log_file = "item_retrievals.csv"
    
    if not os.path.exists(log_file):
        with open(log_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['item_id', 'user_id', 'timestamp'])
    
    with open(log_file, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([item_id, user_id, timestamp])

@router.post("/place", response_model=PlaceItemResponse)
async def place_item(request: PlaceItemRequest):
    try:
        if not request.timestamp:
            request.timestamp = datetime.datetime.now().isoformat()

        cargo_file = "cargo_arrangement.csv"
        containers_file = "imported_containers.csv"

        if not os.path.exists(cargo_file) or not os.path.exists(containers_file):
            print(f"Required files not found")
            return {"success": False}

        cargo_df = pl.read_csv(cargo_file)
        containers_df = pl.read_csv(containers_file)

        print(f"Cargo columns: {cargo_df.columns}")
        print(f"Containers columns: {containers_df.columns}")

        container_data = containers_df.filter(pl.col("container_id") == request.container_id)
        if container_data.is_empty():
            print(f"Container ID {request.container_id} not found")
            return {"success": False}

        container_info = container_data.row(0, named=True)
        zone = container_info["zone"]

        position_str = str(request.position.model_dump())

        start = request.position.startCoordinates
        end = request.position.endCoordinates
        coordinates_str = f"({start.width_cm},{start.depth_cm},{start.height_cm}),({end.width_cm},{end.depth_cm},{end.height_cm})"

        item_exists = not cargo_df.filter(pl.col("item_id") == request.item_id).is_empty()

        overlapping_items = cargo_df.filter(
            (pl.col("zone") == zone) & 
            (pl.col("item_id") != request.item_id)
        )

        overlapping = False
        for item in overlapping_items.iter_rows(named=True):
            item_coordinates = item["coordinates"]
            coordinates = item_coordinates.strip()[1:-1].split("),(")
            item_start = coordinates[0].split(",")
            item_start = (float(item_start[0]), float(item_start[1]), float(item_start[2]))
            item_end = coordinates[1].split(",")
            item_end = (float(item_end[0]), float(item_end[1]), float(item_end[2]))

            start = (start.width_cm, start.depth_cm, start.height_cm)
            end = (end.width_cm, end.depth_cm, end.height_cm)

            if (start[0] < item_end[0] and end[0] > item_start[0] and 
                start[1] < item_end[1] and end[1] > item_start[1] and 
                start[2] < item_end[2] and end[2] > item_start[2]):
                overlapping = True
                break

        if overlapping:
            print(f"Cannot place item {request.item_id} in container {request.container_id} due to overlap")
            return {"success": False}

        if item_exists:
            cargo_df = cargo_df.with_columns([
                pl.when(pl.col("item_id") == request.item_id)
                  .then(pl.lit(zone))
                  .otherwise(pl.col("zone"))
                  .alias("zone"),
                pl.when(pl.col("item_id") == request.item_id)
                  .then(pl.lit(coordinates_str))
                  .otherwise(pl.col("coordinates"))
                  .alias("coordinates")
            ])
        else:
            new_row = pl.DataFrame({
                "item_id": [request.item_id],
                "zone": [zone],
                "coordinates": [coordinates_str]
            })
            cargo_df = pl.concat([cargo_df, new_row])

        cargo_df.write_csv(cargo_file)
        return {"success": True}

    except Exception as e:
        print(f"Error in place endpoint: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {"success": False}