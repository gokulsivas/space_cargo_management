from fastapi import APIRouter, HTTPException, Query, Depends
import polars as pl
import os
import re
from typing import Optional
from schemas import Coordinates, Position, Item_for_search, SearchResponse, RetrievalStep, RetrieveItemRequest, PlaceItemRequest, PlaceItemResponse, CargoPlacementSystem
import datetime
import csv

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
        
        # Define file paths
        items_file = "imported_items.csv"    
        containers_file = "imported_containers.csv"
        cargo_file = "cargo_arrangement.csv"
        waste_file = "waste_items.csv"
        
        # Check if files exist
        if not all(os.path.exists(file) for file in [items_file, cargo_file, containers_file]):
            return {"success": False}
        
        # Load CSV data
        items_df = pl.read_csv(items_file)
        cargo_df = pl.read_csv(cargo_file)
        containers_df = pl.read_csv(containers_file)
        
        # Check if item exists in cargo arrangement
        item_in_cargo = cargo_df.filter(pl.col("itemId") == item_id)
        if item_in_cargo.is_empty():
            return {"success": False}
        
        # Get the item from imported items
        item_data = items_df.filter(pl.col("itemId") == item_id)
        if item_data.is_empty():
            return {"success": False}
        
        # Get current usage limit (ensuring we get it as an integer)
        current_usage = int(item_data.select("usageLimit")[0, 0])
        
        # Debug print to check initial value
        print(f"Initial usage limit for item {item_id}: {current_usage}")
        
        # Check if item has any uses left
        if current_usage <= 0:
            print(f"Item {item_id} has no uses left")
            return {"success": False}
            
        # Decrement usage limit
        new_usage = current_usage - 1
        print(f"New usage limit for item {item_id}: {new_usage}")
        
        updated_items_df = items_df.with_columns(
            pl.when(pl.col("itemId") == item_id)
            .then(pl.lit(new_usage))  
            .otherwise(pl.col("usageLimit"))
            .alias("usageLimit")
        )
        
        # Write updated items data to CSV
        updated_items_df.write_csv(items_file)
        
        # Log the retrieval
        log_retrieval(item_id, user_id, timestamp)
        
        # Only remove from cargo if usage is now 0
        if new_usage == 0:
            print(f"Removing item {item_id} from cargo as it has 0 uses left")
            # Remove from cargo arrangement
            updated_cargo_df = cargo_df.filter(pl.col("itemId") != item_id)
            updated_cargo_df.write_csv(cargo_file)
            
            # Get the zone of the item
            zone = item_in_cargo.select("zone")[0, 0]

            # Get the containerId from the containers data using the zone
            container_id_df = containers_df.filter(pl.col("zone") == zone)
            if container_id_df.is_empty():
                print("Error: No container found for the given zone.")
                if new_usage == 0 and (item_id not in cargo_df["itemId"].to_list()):
                    return {"success": False}

            container_id = container_id_df.select("containerId")[0, 0]
            position_data = item_in_cargo.select("coordinates")[0, 0]
            
            # Add to waste items with the proper format
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


# Helper function to add item to waste tracking

# Fixed add_to_waste_items function
def add_to_waste_items(item_id, name, reason, container_id, position):
    waste_file = "waste_items.csv"
    
    # Create the waste_items.csv if it doesn't exist
    if not os.path.exists(waste_file):
        waste_df = pl.DataFrame({
            "itemId": [int(item_id)],
            "name": [name],
            "reason": [reason],
            "containerId": [str(container_id)],
            "position": [str(position)]
        })
        print("Initial waste_df schema:")
        print(waste_df.schema)
        waste_df.write_csv(waste_file)
        return
    
    # Load existing waste items
    try:
        waste_df = pl.read_csv(waste_file)
        print("Loaded waste_df schema:")
        print(waste_df.schema)
    except:
        waste_df = pl.DataFrame({
            "itemId": [],
            "name": [],
            "reason": [],
            "containerId": [],
            "position": []
        })
        print("Empty waste_df schema:")
        print(waste_df.schema)
    
    # Add new waste item
    new_waste_item = pl.DataFrame({
        "itemId": [int(item_id)],
        "name": [name],
        "reason": [reason],
        "containerId": [str(container_id)],
        "position": [str(position)]
    })

    # Concatenate and save - without trying to cast types
    updated_waste_df = pl.concat([waste_df, new_waste_item])
    updated_waste_df.write_csv(waste_file)
    
    print(f"Added item {item_id} to waste items with reason: {reason}")



# Helper function to log retrievals (optional)
def log_retrieval(item_id, user_id, timestamp):
    # You can implement logging to track retrievals
    log_file = "item_retrievals.csv"
    
    # Create file with headers if it doesn't exist
    if not os.path.exists(log_file):
        with open(log_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['itemId', 'userId', 'timestamp'])
    
    # Append retrieval log
    with open(log_file, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([item_id, user_id, timestamp])


@router.post("/place", response_model=PlaceItemResponse)
async def place_item(
    request: PlaceItemRequest
):
    try:
        # Use current time in ISO format if timestamp not provided
        if not request.timestamp:
            request.timestamp = datetime.datetime.now().isoformat()
        
        # Path to the files
        cargo_file = "cargo_arrangement.csv"
        containers_file = "imported_containers.csv"
        
        # Check if files exist
        if not os.path.exists(cargo_file) or not os.path.exists(containers_file):
            print(f"Required files not found")
            return {"success": False}
        
        # Load and process CSV data
        cargo_df = pl.read_csv(cargo_file)
        containers_df = pl.read_csv(containers_file)
        
        # Print columns for debugging
        print(f"Cargo columns: {cargo_df.columns}")
        print(f"Containers columns: {containers_df.columns}")
        
        # Find the zone for the specified containerId
        container_data = containers_df.filter(pl.col("containerId") == request.containerId)
        if container_data.is_empty():
            print(f"Container ID {request.containerId} not found")
            return {"success": False}
        
        container_info = container_data.row(0, named=True)
        zone = container_info["zone"]
        
        # Prepare position string for storage
        position_str = str(request.position.model_dump())
        
        # Format coordinates string like "(w1,d1,h1),(w2,d2,h2)"
        start = request.position.startCoordinates
        end = request.position.endCoordinates
        coordinates_str = f"({start.width},{start.depth},{start.height}),({end.width},{end.depth},{end.height})"
        
        # Check if item exists in cargo arrangement
        item_exists = not cargo_df.filter(pl.col("itemId") == request.itemId).is_empty()
        
        # Check for overlapping items in the container
        overlapping_items = cargo_df.filter(
            (pl.col("zone") == zone) & 
            (pl.col("itemId") != request.itemId)
        )
        
        overlapping = False
        for item in overlapping_items.iter_rows(named=True):
            item_coordinates = item["coordinates"]
            coordinates = item_coordinates.strip()[1:-1].split("),(")
            item_start = coordinates[0].split(",")
            item_start = (float(item_start[0]), float(item_start[1]), float(item_start[2]))
            item_end = coordinates[1].split(",")
            item_end = (float(item_end[0]), float(item_end[1]), float(item_end[2]))
            
            start = (start.width, start.depth, start.height)
            end = (end.width, end.depth, end.height)
            
            # Check for overlap
            if (start[0] < item_end[0] and end[0] > item_start[0] and 
                start[1] < item_end[1] and end[1] > item_start[1] and 
                start[2] < item_end[2] and end[2] > item_start[2]):
                overlapping = True
                break
        
        if overlapping:
            print(f"Cannot place item {request.itemId} in container {request.containerId} due to overlap")
            return {"success": False}
        
        if item_exists:
            # Update existing item
            cargo_df = cargo_df.with_columns([
                pl.when(pl.col("itemId") == request.itemId)
                  .then(pl.lit(zone))  
                  .otherwise(pl.col("zone"))
                  .alias("zone"),
                pl.when(pl.col("itemId") == request.itemId)
                  .then(pl.lit(coordinates_str))  
                  .otherwise(pl.col("coordinates"))
                  .alias("coordinates")
            ])
        else:
            # Item doesn't exist in cargo arrangement, so add it
            new_row = pl.DataFrame({
                "itemId": [request.itemId],
                "zone": [zone],
                "coordinates": [coordinates_str]
            })
            
            # Add the new row
            cargo_df = pl.concat([cargo_df, new_row])
        
        # Save changes
        cargo_df.write_csv(cargo_file)
        
        return {"success": True}
        
    except Exception as e:
        print(f"Error in place endpoint: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {"success": False}
