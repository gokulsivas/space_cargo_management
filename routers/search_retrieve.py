from fastapi import APIRouter, HTTPException, Query, Depends
import polars as pl
import os
import re
from typing import Optional
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
from algos.retrieve_algo import PriorityAStarRetrieval
from algos.search_algo import ItemSearchSystem
import numpy as np

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
    name: Optional[str] = Query(None)
):
    try:
        # Load all required data
        items_df = pl.read_csv(items_file)
        containers_df = pl.read_csv(containers_file)
        cargo_df = pl.read_csv(cargo_file)
        
        # Convert DataFrames to list of dicts
        items_data = items_df.to_dicts()
        containers_data = containers_df.to_dicts()
        cargo_data = cargo_df.to_dicts()
        
        # Initialize search system with cargo data
        search_system = ItemSearchSystem(
            items_data=items_data,
            containers_data=containers_data,
            cargo_data=cargo_data  # Add cargo data
        )
        
        # Perform search
        if item_id is not None:
            result = search_system.search_by_id(item_id)
        elif name is not None:
            result = search_system.search_by_name(name)
        else:
            raise HTTPException(status_code=400, detail="Either item_id or name must be provided")
            
        # Convert the result to SearchResponse format
        if result["found"]:
            return SearchResponse(
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
                retrieval_steps=[RetrievalStep(**step) for step in result.get("retrieval_steps", [])]
            )
        else:
            return SearchResponse(success=True, found=False)
        
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