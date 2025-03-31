import json
import re
import csv
import os
from fastapi import APIRouter, HTTPException
from typing import List, Dict
import polars as pl
from pydantic import BaseModel
from datetime import datetime
from schemas import Position, ReturnPlanRequest, ReturnPlanResponse, ReturnItem, ReturnPlanStep, RetrievalStep, CompleteUndockingRequest, Object3D, ReturnManifest

router = APIRouter(
    prefix="/api/waste",
    tags=["waste"],
)

def parse_position(position_str: str) -> dict:
    """
    Parse a position string formatted as:
    "(x,y,z),(x,y,z)"
    and return a dict with startCoordinates and endCoordinates.
    """
    pattern = r"\((.*?)\)"
    matches = re.findall(pattern, position_str)

    if len(matches) != 2:
        return {
            "startCoordinates": {"width": 0, "depth": 0, "height": 0},
            "endCoordinates": {"width": 0, "depth": 0, "height": 0}
        }

    try:
        def parse_tuple(tuple_str: str) -> dict:
            values = [float(v) for v in tuple_str.split(",")]
            return {"width": values[0], "depth": values[1], "height": values[2]}
        
        start_coords = parse_tuple(matches[0])
        end_coords = parse_tuple(matches[1])
        
        return {
            "startCoordinates": start_coords,
            "endCoordinates": end_coords
        }
    except Exception as e:
        print(f"Error parsing position tuple: {str(e)}")
        return {
            "startCoordinates": {"width": 0, "depth": 0, "height": 0},
            "endCoordinates": {"width": 0, "depth": 0, "height": 0}
        }

@router.get("/identify")
async def identify_waste():
    waste_file = "waste_items.csv"
    imported_file = "imported_items.csv"
    waste_items = []

    # Load existing waste items from waste_items.csv if it exists.
    if os.path.exists(waste_file):
        try:
            waste_df = pl.read_csv(waste_file)
            if not waste_df.is_empty():
                for item in waste_df.to_dicts():
                    position_value = item.get("position", "")
                    if isinstance(position_value, str):
                        if position_value.strip().startswith("{"):
                            try:
                                position_dict = json.loads(position_value)
                            except Exception as e:
                                print(f"JSON parsing error: {str(e)}")
                                position_dict = {
                                    "startCoordinates": {"width": 0, "depth": 0, "height": 0},
                                    "endCoordinates": {"width": 0, "depth": 0, "height": 0}
                                }
                        elif position_value.strip().startswith("("):
                            position_dict = parse_position(position_value)
                        else:
                            position_dict = {
                                "startCoordinates": {"width": 0, "depth": 0, "height": 0},
                                "endCoordinates": {"width": 0, "depth": 0, "height": 0}
                            }
                    else:
                        position_dict = {
                            "startCoordinates": {"width": 0, "depth": 0, "height": 0},
                            "endCoordinates": {"width": 0, "depth": 0, "height": 0}
                        }
                    
                    position_model = Position(
                        startCoordinates=position_dict.get("startCoordinates", {"width": 0, "depth": 0, "height": 0}),
                        endCoordinates=position_dict.get("endCoordinates", {"width": 0, "depth": 0, "height": 0})
                    )
                    
                    # Fix: Ensure itemId is cast to int safely with default value
                    try:
                        item_id = int(item.get("itemId", "0"))
                    except ValueError:
                        item_id = 0
                    
                    formatted_item = {
                        "itemId": item_id,
                        "name": str(item.get("name", "")),
                        "reason": str(item.get("reason", "")),
                        "containerId": str(item.get("containerId", "")),
                        "position": position_model.dict()
                    }
                    waste_items.append(formatted_item)
        except Exception as e:
            print(f"Error reading waste_items.csv: {str(e)}")
    
    # Now, check imported_items.csv for expired items.
    if os.path.exists(imported_file):
        try:
            imported_df = pl.read_csv(imported_file)
            if "expiryDate" in imported_df.columns:
                current_date = datetime.now().date()
                # Filter rows where expiryDate (formatted as DD-MM-YY) is before the current date
                expired_df = imported_df.filter(
                    pl.col("expiryDate").str.strptime(pl.Date, format="%d-%m-%y") < current_date
                )
                
                for item in expired_df.to_dicts():
                    # Lookup containerId from imported_containers.csv using the preferredZone field.
                    container_id = ""
                    if os.path.exists("imported_containers.csv"):
                        try:
                            containers_df = pl.read_csv("imported_containers.csv")
                            # Assume imported_containers.csv has columns: containerId, zone, ...
                            matching_container = containers_df.filter(pl.col("zone") == item.get("preferredZone", "")).to_dicts()
                            if matching_container:
                                container_id = str(matching_container[0].get("containerId", ""))
                        except Exception as e:
                            print(f"Error reading imported_containers.csv: {str(e)}")
                    
                    # Lookup coordinates from cargo_arrangement.csv using the item's itemId.
                    coordinates = {
                        "startCoordinates": {"width": 0, "depth": 0, "height": 0},
                        "endCoordinates": {"width": 0, "depth": 0, "height": 0}
                    }
                    if os.path.exists("cargo_arrangement.csv"):
                        try:
                            cargo_df = pl.read_csv("cargo_arrangement.csv")
                            # Fix: Cast both sides to string for comparison
                            cargo_matching = cargo_df.filter(pl.col("itemId").cast(pl.Utf8) == str(item.get("itemId", ""))).to_dicts()
                            print(f"cargo_matching: {cargo_matching}")
                            if cargo_matching:
                                pos_str = cargo_matching[0].get("coordinates", "")
                                if pos_str:
                                    coordinates = parse_position(pos_str)
                        except Exception as e:
                            print(f"Error reading cargo_arrangement.csv: {str(e)}")
                    
                    # Fix: Ensure itemId is cast to int safely with default value
                    try:
                        item_id = int(item.get("itemId", "0"))
                    except ValueError:
                        item_id = 0
                    
                    expired_item = {
                        "itemId": item_id,
                        "name": str(item.get("name", "")),
                        "reason": "Expired",
                        "containerId": container_id,
                        "position": coordinates
                    }
                    if not any(w["itemId"] == expired_item["itemId"] for w in waste_items):
                        waste_items.append(expired_item)
        except Exception as e:
            print(f"Error processing imported_items.csv for expiry: {str(e)}")
    
    return {"success": True, "wasteItems": waste_items}

def calculate_volume(obj):
    width = abs(obj.end["width"] - obj.start["width"])
    depth = abs(obj.end["depth"] - obj.start["depth"])
    height = abs(obj.end["height"] - obj.start["height"])
    return width * depth * height

def load_imported_items(filename):
    imported_items = {}
    if not os.path.exists(filename):
        return imported_items
    
    with open(filename, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Fix: Ensure proper handling of empty itemId
            item_id = row.get("itemId", "")
            if item_id:
                try:
                    mass = float(row.get("mass", 0))
                except ValueError:
                    mass = 0
                imported_items[item_id] = mass
    
    return imported_items

def read_waste_data(waste_filename, imported_filename):
    objects = []
    imported_items = load_imported_items(imported_filename)
    weights = {}

    if not os.path.exists(waste_filename):
        return objects, weights
    
    with open(waste_filename, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            coordinates = parse_position(row.get("position", ""))
            item_id = row.get("itemId", "")
            weight = imported_items.get(item_id, 0)  # Store weight separately
            obj = Object3D(
                item_id,
                row.get("name", ""),
                row.get("containerId", ""),
                coordinates["startCoordinates"],
                coordinates["endCoordinates"]
            )
            objects.append(obj)
            weights[item_id] = weight

    return objects, weights

@router.post("/return-plan", response_model=ReturnPlanResponse)
async def generate_return_plan(request: ReturnPlanRequest):
    waste_objects_all, weights = read_waste_data("waste_items.csv", "imported_items.csv")
    waste_objects = [obj for obj in waste_objects_all if obj.containerId == request.undockingContainerId]
    
    return_plan = []
    retrieval_steps = []
    return_items = []
    total_volume = 0
    total_weight = 0
    step_counter = 1
    
    while waste_objects:
        front_obj = min(waste_objects, key=lambda obj: obj.front_z, default=None)
        front_weight = weights.get(front_obj.itemId, 0) if front_obj else 0

        if front_obj and total_weight + front_weight <= request.maxWeight:
            retrieval_steps.append(RetrievalStep(step=step_counter, action="remove", itemId=front_obj.itemId, itemName=front_obj.name))
            return_plan.append(ReturnPlanStep(
                step=step_counter,
                itemId=front_obj.itemId,
                itemName=front_obj.name,
                fromContainer=request.undockingContainerId,
                toContainer=front_obj.containerId
            ))
            return_items.append(ReturnItem(itemId=front_obj.itemId, name=front_obj.name, reason="Out of use"))
            total_weight += front_weight
            total_volume += calculate_volume(front_obj)
            waste_objects.remove(front_obj)
            step_counter += 1
    
    manifest = ReturnManifest(
        undockingContainerId=request.undockingContainerId,
        undockingDate=request.undockingDate,
        returnItems=return_items,
        totalVolume=total_volume,
        totalWeight=total_weight
    )
    
    return ReturnPlanResponse(
        success=True,
        returnPlan=return_plan,
        retrievalSteps=retrieval_steps,
        returnManifest=manifest
    )

@router.post("/complete-undocking")
async def complete_undocking(request: CompleteUndockingRequest):
    waste_file = "waste_items.csv"
    items_file = "imported_items.csv"
    items_count = 0
    
    if os.path.exists(waste_file):
        try:
            waste_items_df = pl.read_csv(waste_file)
            if not waste_items_df.is_empty():
                filtered_df = waste_items_df.filter(pl.col("containerId") == request.undockingContainerId)
                items_count = filtered_df.height
                updated_df = waste_items_df.filter(pl.col("containerId") != request.undockingContainerId)
                updated_df.write_csv(waste_file)
        except Exception as e:
            print(f"Error processing waste items: {str(e)}")
    
    if os.path.exists(items_file):
        try:
            items_df = pl.read_csv(items_file)
            if "usageCount" in items_df.columns and "usageLimit" in items_df.columns:
                expired_items = items_df.filter(
                    (pl.col("usageCount") >= pl.col("usageLimit")) & 
                    (pl.col("containerId") == request.undockingContainerId)
                )
                
                if not expired_items.is_empty():
                    new_waste_items = []
                    
                    for item in expired_items.to_dicts():
                        position_str = f"(0,0,0),(0,0,0)"
                        new_waste_item = {
                            "itemId": item["itemId"],
                            "name": item["name"] if "name" in item else f"Item {item['itemId']}",
                            "reason": "Usage limit reached",
                            "containerId": item["containerId"],
                            "position": position_str
                        }
                        new_waste_items.append(new_waste_item)
                    
                    new_waste_df = pl.DataFrame(new_waste_items)
                    
                    if os.path.exists(waste_file) and not pl.read_csv(waste_file).is_empty():
                        combined_df = pl.concat([pl.read_csv(waste_file), new_waste_df])
                        combined_df.write_csv(waste_file)
                    else:
                        new_waste_df.write_csv(waste_file)
                    
                    items_count += new_waste_df.height
                    
                    items_df = items_df.filter(
                        ~((pl.col("usageCount") >= pl.col("usageLimit")) & 
                          (pl.col("containerId") == request.undockingContainerId))
                    )
                    items_df.write_csv(items_file)
        
        except Exception as e:
            print(f"Error processing items at usage limit: {str(e)}")
    
    return {"success": True, "itemsRemoved": items_count}