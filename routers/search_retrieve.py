from fastapi import APIRouter, HTTPException, Query, Depends
import polars as pl
import os
import re
from typing import Optional
from schemas import Coordinates, Position, Item_for_search, SearchResponse, RetrievalStep, RetrieveItemRequest
import datetime

router = APIRouter(
    prefix="/api",
    tags=["search_retrieve"],
)

cargo_file = "cargo_arrangement.csv"

@router.get("/search", response_model=SearchResponse)
async def search_item(
    item_id: Optional[int] = Query(None, description="ID of the item to search for"),
    name: Optional[str] = Query(None, description="Name of the item to search for"),
    user_id: Optional[str] = Query(None, description="Optional user ID")
):
    # Validate that at least one search parameter is provided
    if item_id is None and name is None:
        raise HTTPException(status_code=400, detail="Either item_id or name must be provided")
    
    # Path to the CSV data files
    items_file = "imported_items.csv"
    containers_file = "imported_containers.csv"
    
    # Check if data files exist
    for file_path in [cargo_file, items_file, containers_file]:
        if not os.path.exists(file_path):
            print(f"Data file {file_path} not found")
            return SearchResponse(success=False, found=False)
    
    try:
        # Load data from all CSV files with correct columns
        cargo_df = pl.read_csv(cargo_file)
        items_df = pl.read_csv(items_file)
        containers_df = pl.read_csv(containers_file)
        
        # Print columns for debugging
        print(f"Available cargo columns: {cargo_df.columns}")
        print(f"Available items columns: {items_df.columns}")
        print(f"Available containers columns: {containers_df.columns}")
        
        # Find the item based on provided parameters
        target_item_id = None
        target_item_name = None
        target_zone = None
        target_coordinates = None
        
        # Step 1: First find the item ID (if we need to search by name)
        if item_id is not None:
            target_item_id = item_id
            # Check if the item exists in items.csv
            item_data = items_df.filter(pl.col("itemId") == item_id)
            if not item_data.is_empty():
                target_item_name = item_data.row(0, named=True)["name"]
            else:
                print(f"Item with ID {item_id} not found in items.csv")
                return SearchResponse(success=True, found=False)
        else:
            # Search by name in items.csv
            item_data = items_df.filter(pl.col("name") == name)
            if not item_data.is_empty():
                item_info = item_data.row(0, named=True)
                target_item_id = item_info["itemId"]
                target_item_name = name
            else:
                print(f"Item with name '{name}' not found in items.csv")
                return SearchResponse(success=True, found=False)
        
        # Step 2: Now find the item in cargo.csv
        cargo_item = cargo_df.filter(pl.col("itemId") == target_item_id)
        if cargo_item.is_empty():
            print(f"Item with ID {target_item_id} not found in cargo.csv")
            return SearchResponse(success=True, found=False)
        
        cargo_info = cargo_item.row(0, named=True)
        target_zone = cargo_info["zone"]
        
        # Parse coordinates from string format "(W1,D1,H1),(W2,D2,H2)"
        if "coordinates" in cargo_info:
            coord_str = cargo_info["coordinates"]
            print(coord_str)
            # Extract numbers using regex
            coords = re.findall(r'[-+]?\d*\.\d+|[-+]?\d+', coord_str)
            print(coords)
            if len(coords) >= 6:
                w1, d1, h1, w2, d2, h2 = map(float, coords[:6])
                start_coords = Coordinates(width=w1, depth=d1, height=h1)
                end_coords = Coordinates(width=w2, depth=d2, height=h2)
            else:
                # Fallback if parsing fails
                print(f"Could not parse coordinates: {coord_str}")
        else:
            ## TODO  add json error msg
            print(f"Coordinates not found in cargo item data")
        
        # Step 3: Find container ID based on zone in containers.csv
        container_id = None
        container_data = containers_df.filter(pl.col("zone") == target_zone)
        if not container_data.is_empty():
            container_id = container_data.row(0, named=True)["containerId"]
        else:
            print(f"Container for zone {target_zone} not found in containers.csv")
            # We'll still proceed, but with unknown container ID
        
        # Find potentially blocking items in the same zone
        blocking_items = cargo_df.filter(
            (pl.col("zone") == target_zone) & 
            (pl.col("itemId") != target_item_id)
        )
        
        # Generate retrieval steps
        retrieval_steps = []
        step_counter = 1
        
        # Process blocking items if any found
        if not blocking_items.is_empty():
            # Step 1: Remove blocking items
            for blocking_item in blocking_items.iter_rows(named=True):
                # Get blocking item name from imported_items.csv
                blocking_item_name = "Unknown"
                blocking_item_data = items_df.filter(pl.col("itemId") == blocking_item["itemId"])
                if not blocking_item_data.is_empty():
                    blocking_item_name = blocking_item_data.row(0, named=True).get("name", f"Item {blocking_item['itemId']}")
                
                retrieval_steps.append(
                    RetrievalStep(
                        step=step_counter,
                        action="setAside",
                        itemId=blocking_item["itemId"],
                        itemName=blocking_item_name
                    )
                )
                step_counter += 1
        
        # Step 2: Retrieve the target item
        retrieval_steps.append(
            RetrievalStep(
                step=step_counter,
                action="retrieve",
                itemId=target_item_id,
                itemName=target_item_name
            )
        )
        step_counter += 1
        
        # Step 3: Place back the removed items (in reverse order)
        for blocking_step in reversed(retrieval_steps[:-1]):  # All except the target item step
            retrieval_steps.append(
                RetrievalStep(
                    step=step_counter,
                    action="placeBack",
                    itemId=blocking_step.itemId,
                    itemName=blocking_step.itemName
                )
            )
            step_counter += 1
        
        # Create the item object
        item = Item_for_search(
            itemId=target_item_id,
            name=target_item_name,
            containerId=container_id if container_id else "unknown",
            zone=target_zone,
            position=Position(
                startCoordinates=dict(start_coords),
                endCoordinates=dict(end_coords)
            )
        )
        print(f"Item found: {item}")
        
        print(f"Response created with {len(retrieval_steps)} retrieval steps")
        return SearchResponse(
            success=True,
            found=True,
            item=item,
            retrievalSteps=retrieval_steps
        )
        
    except Exception as e:
        # Enhanced error logging
        print(f"Error in search endpoint: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return SearchResponse(success=False, found=False)


@router.post("/retrieve")
async def retrieve_item(
    request: RetrieveItemRequest
):
    try:
        # Extract data from request
        item_id = request.itemId
        user_id = request.userId
        timestamp = request.timestamp
        
        # Use current time in ISO format if timestamp not provided
        if not timestamp:
            timestamp = datetime.datetime.now().isoformat()
        
        # Path to the cargo arrangement CSV
        cargo_file = "cargo_arrangement.csv"
        
        # Check if file exists
        if not os.path.exists(cargo_file):
            return {"success": False}
        
        # Load and process CSV data
        cargo_df = pl.read_csv(cargo_file)
        
        # Check if item exists
        if cargo_df.filter(pl.col("itemId") == item_id).is_empty():
            return {"success": False}
        
        # Remove the item from the dataframe
        updated_df = cargo_df.filter(pl.col("itemId") != item_id)
        
        # Write the updated dataframe back to CSV
        updated_df.write_csv(cargo_file)
        
        # Return response in the specified format
        return {"success": True}
        
    except Exception as e:
        print(f"Error in retrieve endpoint: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {"success": False}

"""@router.post("/place")
async def place_item(
    itemId: str, 
    userId: str, 
    timestamp: str, 
    containerId: str, 
    position: dict,
    cargo_system: CargoPlacementSystem = Depends(get_cargo_system)
):
    result_df = cargo_system.items_df.filter(pl.col("itemId") == itemId)
    if result_df.is_empty():
        raise HTTPException(status_code=404, detail="Item not found.")

    if "containerId" not in cargo_system.items_df.columns:
        cargo_system.items_df = cargo_system.items_df.with_columns(pl.lit("unknown").alias("containerId"))

    if "position" not in cargo_system.items_df.columns:
        cargo_system.items_df = cargo_system.items_df.with_columns(pl.lit(None).alias("position"))

    cargo_system.items_df = cargo_system.items_df.with_columns(
        (pl.when(pl.col("itemId") == itemId).then(containerId).otherwise(pl.col("containerId"))).alias("containerId"),
        (pl.when(pl.col("itemId") == itemId).then(str(position)).otherwise(pl.col("position"))).alias("position")
    )

    cargo_system.items_df.write_csv(ITEMS_CSV_PATH)

    return {"success": True}"""