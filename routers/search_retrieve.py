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
import datetime
import csv
from algos.retrieve_algo import PriorityAStarRetrieval, RetrievalPath
from algos.search_algo import ItemSearchSystem
import numpy as np
import pandas as pd

router = APIRouter(
    prefix="/api",
    tags=["search_retrieve"],
)

cargo_file = "cargo_arrangement.csv"
items_file = "imported_items.csv"
containers_file = "imported_containers.csv"

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
                    ) for step in (result.get("retrieval_steps") or [])
                ]
            )
            
            # Log the search if user_id is provided
            if user_id:
                from routers.logs import log_action
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
        temp_cargo_file = "temp_cargo_arrangement.csv"
        waste_file = "waste_items.csv"

        # Check if required files exist
        if not os.path.exists(items_file) or not os.path.exists(containers_file):
            print(f"Missing required files. Please ensure all files exist.")
            return {"success": False}

        # For retrieval, we'll prefer the temp cargo file if it exists, as it maintains original usage limits
        cargo_read_file = temp_cargo_file if os.path.exists(temp_cargo_file) else cargo_file

        # Load CSV data
        items_df = pl.read_csv(items_file)
        cargo_df = pl.read_csv(cargo_read_file)
        containers_df = pl.read_csv(containers_file)
        
        print(f"Reading cargo data from: {cargo_read_file}")

        # Check if item exists in cargo
        item_in_cargo = cargo_df.filter(pl.col("item_id") == item_id)
        if item_in_cargo.is_empty():
            return {"success": False}

        # Check if item exists in items database
        item_data = items_df.filter(pl.col("item_id") == item_id)
        if item_data.is_empty():
            print(f"Item {item_id} not found in items database")
            return {"success": False}

        # Get zone and container information
        zone = item_in_cargo.select("zone")[0, 0]
        container_data = containers_df.filter(pl.col("zone") == zone)
        if container_data.is_empty():
            print(f"No container found for zone {zone}")
            return {"success": False}

        # Initialize retrieval algorithm with container dimensions
        container_dims = container_data.row(0, named=True)
        retriever = PriorityAStarRetrieval({
            "width_cm": float(container_dims["width_cm"]),
            "depth_cm": float(container_dims["depth_cm"]),
            "height_cm": float(container_dims["height_cm"])
        })

        # Parse item coordinates
        coord_str = item_in_cargo.select("coordinates")[0, 0]
        print(f"Item coordinates: {coord_str}")
        coords = re.findall(r'[-+]?\d*\.\d+|[-+]?\d+', coord_str)
        
        if len(coords) < 6:
            print(f"Invalid coordinates format: {coord_str}")
            return {"success": False}

        # Check usage limit and update
        current_usage = int(items_df.filter(pl.col("item_id") == item_id).select("usage_limit")[0, 0])
        if current_usage <= 0:
            return {"success": False}

        # Update usage limit in the items file
        new_usage = current_usage - 1
        print(f"New usage limit for item {item_id}: {new_usage}")

        updated_items_df = items_df.with_columns(
            pl.when(pl.col("item_id") == item_id)
            .then(pl.lit(new_usage))
            .otherwise(pl.col("usage_limit"))
            .alias("usage_limit")
        )

        # Write updated items data
        updated_items_df.write_csv(items_file)
        log_retrieval(item_id, user_id, timestamp)

        # Handle items with no uses left - only update the main cargo file
        if new_usage == 0:
            print(f"Removing item {item_id} from main cargo file as it has 0 uses left")
            # Load the main cargo file for updating
            main_cargo_df = pl.read_csv(cargo_file)
            updated_cargo_df = main_cargo_df.filter(pl.col("item_id") != item_id)
            updated_cargo_df.write_csv(cargo_file)

            container_id = container_data.select("container_id")[0, 0]
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
        temp_cargo_file = "temp_cargo_arrangement.csv"
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

        # Get coordinates from the request's Position object
        start_coords = request.position.startCoordinates
        end_coords = request.position.endCoordinates
        
        # Create coordinate string in the expected format
        coordinates_str = f"({start_coords.width_cm},{start_coords.depth_cm},{start_coords.height_cm}),({end_coords.width_cm},{end_coords.depth_cm},{end_coords.height_cm})"

        item_exists = not cargo_df.filter(pl.col("item_id") == request.item_id).is_empty()

        overlapping_items = cargo_df.filter(
            (pl.col("zone") == zone) & 
            (pl.col("item_id") != request.item_id)
        )

        print(f"Checking for overlaps in container {request.container_id} at zone {zone}")
        print(f"New item position: start={start_coords}, end={end_coords}")

        overlapping = False
        for item in overlapping_items.iter_rows(named=True):
            item_coordinates = item["coordinates"]
            coordinates = item_coordinates.strip()[1:-1].split("),(")
            item_start = coordinates[0].split(",")
            item_start = (float(item_start[0]), float(item_start[1]), float(item_start[2]))
            item_end = coordinates[1].split(",")
            item_end = (float(item_end[0]), float(item_end[1]), float(item_end[2]))

            # Create tuples for comparison
            start = (start_coords.width_cm, start_coords.depth_cm, start_coords.height_cm)
            end = (end_coords.width_cm, end_coords.depth_cm, end_coords.height_cm)

            print(f"Checking against item {item['item_id']} at coordinates {item_coordinates}")
            print(f"Item start: {item_start}, Item end: {item_end}")
            print(f"New item start: {start}, New item end: {end}")

            # Check if the new item's position overlaps with existing items
            # Using inclusive inequalities to handle adjacent items correctly
            if (start[0] <= item_end[0] and end[0] >= item_start[0] and 
                start[1] <= item_end[1] and end[1] >= item_start[1] and 
                start[2] <= item_end[2] and end[2] >= item_start[2]):
                print(f"Overlap detected with item {item['item_id']} at coordinates {item_coordinates}")
                overlapping = True
                break

        if overlapping:
            print(f"Cannot place item {request.item_id} in container {request.container_id} due to overlap")
            return {"success": False}

        # Update the main cargo arrangement file
        if item_exists:
            # For the main cargo file
            updated_cargo_df = cargo_df.with_columns([
                pl.when(pl.col("item_id") == request.item_id)
                  .then(pl.lit(zone))
                  .otherwise(pl.col("zone"))
                  .alias("zone"),
                pl.when(pl.col("item_id") == request.item_id)
                  .then(pl.lit(coordinates_str))
                  .otherwise(pl.col("coordinates"))
                  .alias("coordinates")
            ])
            updated_cargo_df.write_csv(cargo_file)
        else:
            new_row = pl.DataFrame({
                "item_id": [request.item_id],
                "zone": [zone],
                "coordinates": [coordinates_str]
            })
            updated_cargo_df = pl.concat([cargo_df, new_row])
            updated_cargo_df.write_csv(cargo_file)
        
        # Also update the temp cargo arrangement file if it exists
        if os.path.exists(temp_cargo_file):
            try:
                temp_cargo_df = pl.read_csv(temp_cargo_file)
                temp_item_exists = not temp_cargo_df.filter(pl.col("item_id") == request.item_id).is_empty()
                
                if temp_item_exists:
                    # Update existing item in temp file
                    updated_temp_df = temp_cargo_df.with_columns([
                        pl.when(pl.col("item_id") == request.item_id)
                          .then(pl.lit(zone))
                          .otherwise(pl.col("zone"))
                          .alias("zone"),
                        pl.when(pl.col("item_id") == request.item_id)
                          .then(pl.lit(coordinates_str))
                          .otherwise(pl.col("coordinates"))
                          .alias("coordinates")
                    ])
                    updated_temp_df.write_csv(temp_cargo_file)
                else:
                    # Add new item to temp file
                    new_row = pl.DataFrame({
                        "item_id": [request.item_id],
                        "zone": [zone],
                        "coordinates": [coordinates_str]
                    })
                    updated_temp_df = pl.concat([temp_cargo_df, new_row])
                    updated_temp_df.write_csv(temp_cargo_file)
                
                print(f"Updated both {cargo_file} and {temp_cargo_file}")
            except Exception as e:
                print(f"Error updating temp cargo file: {str(e)}")
                print(f"Only updated the main cargo file")
        else:
            # Just copy the main file to the temp file
            updated_cargo_df.write_csv(temp_cargo_file)
            print(f"Created new {temp_cargo_file} as a copy of {cargo_file}")

        return {"success": True}

    except Exception as e:
        print(f"Error in place endpoint: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {"success": False}