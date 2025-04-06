from fastapi import APIRouter, HTTPException
import pandas as pd
import os
from typing import List, Dict
from pydantic import BaseModel

router = APIRouter()

class ContainerItem(BaseModel):
    container_id: str
    item_id: int
    start_width_cm: float
    end_width_cm: float
    start_height_cm: float
    end_height_cm: float
    start_depth_cm: float
    end_depth_cm: float

class ContainerResponse(BaseModel):
    containers: List[str]
    items: Dict[str, List[ContainerItem]]
    dimensions: Dict[str, Dict[str, float]]

@router.get("/items", response_model=ContainerResponse)
async def get_container_items():
    try:
        # Get the workspace root directory (parent of space-hack)
        workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        containers_file = os.path.join(workspace_root, "space_cargo_management", "imported_containers.csv")
        cargo_file = os.path.join(workspace_root, "space_cargo_management", "cargo_arrangement.csv")

        print(f"Looking for containers file at: {containers_file}")  # Debug print
        
        # Read container dimensions
        containers_df = pd.read_csv(containers_file)
        
        # Get unique container IDs and their dimensions
        container_ids = sorted(containers_df['container_id'].unique())
        container_dimensions = {}
        
        for _, container in containers_df.iterrows():
            container_dimensions[container['container_id']] = {
                'width': float(container['width_cm']),
                'height': float(container['height_cm']),
                'depth': float(container['depth_cm'])
            }

        # Initialize items dictionary
        items_by_container = {container_id: [] for container_id in container_ids}

        try:
            # Try to read cargo arrangement if file exists
            cargo_df = pd.read_csv(cargo_file)
            for _, row in cargo_df.iterrows():
                if row['container_id'] in container_ids:
                    item = ContainerItem(
                        container_id=str(row['container_id']),
                        item_id=int(row['item_id']),
                        start_width_cm=float(row['start_width_cm']),
                        end_width_cm=float(row['end_width_cm']),
                        start_height_cm=float(row['start_height_cm']),
                        end_height_cm=float(row['end_height_cm']),
                        start_depth_cm=float(row['start_depth_cm']),
                        end_depth_cm=float(row['end_depth_cm'])
                    )
                    items_by_container[row['container_id']].append(item)
        except (FileNotFoundError, pd.errors.EmptyDataError):
            # If cargo arrangement file doesn't exist or is empty, continue with empty items
            pass

        return {
            "containers": container_ids,
            "items": items_by_container,
            "dimensions": container_dimensions
        }
    except FileNotFoundError as e:
        print(f"File not found error: {str(e)}")  # Debug print
        raise HTTPException(status_code=404, detail=f"Container information file not found: {str(e)}")
    except Exception as e:
        print(f"Error in get_container_items: {str(e)}")  # Debug print
        raise HTTPException(status_code=500, detail=str(e)) 