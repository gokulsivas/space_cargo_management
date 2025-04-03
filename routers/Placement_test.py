import logging
import os
# import pickle # No longer needed for saving
import traceback
from typing import List, Dict, Optional, Tuple
from collections import defaultdict # Ensure defaultdict is imported

# --- FastAPI Imports ---
from fastapi import APIRouter, HTTPException, Depends

# --- Placement Algorithm Imports ---
# Make sure placement_algo_v2.py is accessible
try:
    from placement_algo_v2 import AdvancedCargoPlacement, DependencyGraph
except ImportError:
    logging.error("CRITICAL: Failed to import AdvancedCargoPlacement or DependencyGraph from placement_algo_v2.py.")
    AdvancedCargoPlacement = None
    DependencyGraph = None

# --- Schema Imports (Assuming these exist in 'schemas.py') ---
try:
    from schemas import PlacementRequest, PlacementResponse, ItemPlacementResult, ContainerDetails, ItemDetails
except ImportError:
    logging.warning("Could not import schemas. Using placeholder classes.")
    from pydantic import BaseModel, Field
    class ContainerDetails(BaseModel):
        container_id: str
        zone: Optional[str] = None
        width_cm: float
        depth_cm: float
        height_cm: float

    class ItemDetails(BaseModel):
        item_id: str
        container_id: str
        width: float
        depth: float
        height: float
        item_name: Optional[str] = None
        zone: Optional[str] = None

    class PlacementRequest(BaseModel):
        items: List[ItemDetails]
        containers: List[ContainerDetails]

    class ItemPlacementResult(BaseModel):
        item_id: str
        container_id: str
        item_name: Optional[str] = None
        position_x: float
        position_y: float
        position_z: float
        width: float
        depth: float
        height: float

    class PlacementResponse(BaseModel):
        placements: List[ItemPlacementResult]
        errors: Optional[List[str]] = None


# --- Configuration ---
# GRAPH_OUTPUT_DIR = 'dependency_graphs' # No longer needed for saving
# os.makedirs(GRAPH_OUTPUT_DIR, exist_ok=True) # No longer needed

# --- In-Memory Storage for Dependency Graphs ---
# WARNING: This simple dictionary store is not suitable for multi-process/worker deployments (e.g., gunicorn with multiple workers)
# as each worker would have its own separate copy. Consider Redis, Memcached, or another shared store for such scenarios.
dependency_graph_store: Dict[str, DependencyGraph] = {}


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- FastAPI Router ---
router = APIRouter(
    prefix="/api/placement",
    tags=["placement"],
)

# --- Helper Function for Core Placement Logic ---

def perform_placement_for_container(
    container: ContainerDetails,
    items_in_container: List[ItemDetails]
) -> Tuple[Optional[List[ItemPlacementResult]], Optional[str]]:
    """
    Performs placement for a single container and stores its dependency graph in memory.

    Args:
        container: The container details.
        items_in_container: List of items designated for this container.

    Returns:
        A tuple: (list_of_placements, error_message).
        list_of_placements is None if a critical error occurred.
        error_message contains details if placement failed.
    """
    global dependency_graph_store # Declare intent to modify the global variable

    if AdvancedCargoPlacement is None or DependencyGraph is None:
        error = "Placement algorithm components are not loaded due to import error."
        logging.error(error)
        return None, error

    container_id = container.container_id
    logging.info(f"Starting placement for container {container_id} with {len(items_in_container)} items.")

    # --- Prepare Inputs for Algorithm ---
    try:
        container_dims = {
            'width': float(container.width_cm),
            'depth': float(container.depth_cm),
            'height': float(container.height_cm)
        }
        items_list_dict = [item.model_dump() for item in items_in_container]
    except (ValueError, TypeError, AttributeError) as e:
        error = f"Invalid container dimensions or item data for container {container_id}: {e}"
        logging.error(error)
        return None, error

    # --- Run Placement Algorithm ---
    placer = AdvancedCargoPlacement(container_dims)
    placement_result = None
    error_message = None
    try:
        placement_result = placer.place_items(items_list_dict)
    except Exception as e:
        logging.error(f"Error during place_items for container {container_id}: {e}", exc_info=True)
        error_message = f"Placement algorithm failed for container {container_id}: {e}"

    # --- Process Results ---
    if placement_result is None:
        logging.error(f"Placement algorithm returned None for container {container_id}.")
        if not error_message:
             error_message = f"Placement algorithm failed unexpectedly for container {container_id}."
        return None, error_message

    placed_items_dict, dependency_graph = placement_result

    # Check for partial placement or complete failure
    if placed_items_dict is None or not placed_items_dict:
        warning_msg = f"Placement failed or resulted in no items placed for container {container_id}."
        logging.warning(warning_msg)
        if placed_items_dict is not None and len(placed_items_dict) != len(items_in_container):
            error_message = (f"Placement incomplete for container {container_id}. "
                           f"Placed {len(placed_items_dict)} out of {len(items_in_container)}.")
            logging.error(error_message)
            # Proceed to store partial results graph but report error
        elif placed_items_dict is None:
             error_message = f"Placement failed completely for container {container_id} (no items placed)."
             return [], error_message
        else:
             error_message = f"Placement resulted in no items placed for container {container_id}."
             return [], error_message

    # If we reach here, placement was at least partially successful
    logging.info(f"Placement successful for container {container_id}. Placed {len(placed_items_dict)} items.")

    # --- Store Dependency Graph in Memory ---
    try:
        # Store the generated graph object in the global dictionary
        dependency_graph_store[container_id] = dependency_graph
        logging.info(f"Stored dependency graph for container {container_id} in memory.")
    except Exception as e:
        # Handle potential errors during dictionary insertion, though unlikely
        store_error = f"Failed to store dependency graph in memory for container {container_id}: {e}"
        logging.error(store_error, exc_info=True)
        # Append this error to any existing placement errors
        error_message = f"{error_message}. {store_error}" if error_message else store_error
        # Decide if this failure is critical. If so: return None, error_message

    # --- Format Output ---
    placement_results_list = []
    original_item_details = {item.item_id: item for item in items_in_container}

    for item_id, info in placed_items_dict.items():
        pos = info['pos']
        original_item = original_item_details.get(item_id)
        placement_results_list.append(ItemPlacementResult(
            item_id=item_id,
            container_id=container_id,
            item_name=original_item.item_name if original_item else 'N/A',
            position_x=pos[0],
            position_y=pos[1],
            position_z=pos[2],
            width=info['item']['width'],
            depth=info['item']['depth'],
            height=info['item']['height'],
        ))

    return placement_results_list, error_message


# --- API Endpoint ---

@router.post("/", response_model=PlacementResponse)
async def process_placement(request: PlacementRequest) -> PlacementResponse:
    """
    Receives container and item details, performs placement using the
    AdvancedCargoPlacement algorithm, stores dependency graphs in memory,
    and returns the placement results.
    """
    if not request.items or not request.containers:
        raise HTTPException(status_code=400, detail="Items and containers must be provided.")

    all_placements: List[ItemPlacementResult] = []
    all_errors: List[str] = []
    items_by_container = defaultdict(list)
    for item in request.items:
        items_by_container[item.container_id].append(item)

    for container in request.containers:
        container_id = container.container_id
        items_for_this_container = items_by_container.get(container_id, [])

        if not items_for_this_container:
            logging.warning(f"No items provided for container {container_id} in the request. Skipping.")
            continue

        try:
            placement_list, error_msg = perform_placement_for_container(
                container=container,
                items_in_container=items_for_this_container
            )

            if placement_list is not None:
                 all_placements.extend(placement_list)
            if error_msg:
                 all_errors.append(error_msg)
                 if placement_list is None:
                      logging.error(f"Critical error processing container {container_id}. Aborting request.")
                      raise HTTPException(status_code=500, detail=f"Placement failed for container {container_id}: {error_msg}")

        except HTTPException:
             # Re-raise HTTPExceptions directly
             raise
        except Exception as e:
            logging.error(f"Unexpected error processing container {container_id}: {e}", exc_info=True)
            all_errors.append(f"Server error processing container {container_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Internal server error while processing container {container_id}.")

    if not all_placements and not all_errors:
         logging.warning("Placement request processed, but no items were placed (possibly none assigned).")
         return PlacementResponse(placements=[], errors=None)

    return PlacementResponse(placements=all_placements, errors=all_errors if all_errors else None)


# --- Optional: Endpoint to retrieve graph info from memory (for debugging/retrieval) ---
@router.get("/graph/{container_id}", tags=["debug", "placement"])
async def get_dependency_graph_info(container_id: str):
    """Retrieves basic info about a stored dependency graph from memory."""
    global dependency_graph_store
    if container_id in dependency_graph_store:
        graph = dependency_graph_store[container_id]
        try:
            # Return some basic info, not the whole complex object directly via JSON
            return {
                "container_id": container_id,
                "message": "Graph found in memory.",
                "node_count": len(set(graph.blocking_depends_on.keys()) | set(graph.blocks.keys())),
                "blocking_dependency_count": sum(len(v) for v in graph.blocking_depends_on.values()),
                "support_dependency_count": sum(len(v) for v in graph.support_depends_on.values()),
            }
        except Exception as e:
             raise HTTPException(status_code=500, detail=f"Error accessing graph data for {container_id}: {e}")
    else:
        raise HTTPException(status_code=404, detail=f"Dependency graph for container {container_id} not found in memory.")

# --- Optional: Endpoint to clear the in-memory store ---
@router.delete("/graph/clear_all", tags=["debug", "placement"])
async def clear_all_graphs():
    """Clears all dependency graphs from the in-memory store."""
    global dependency_graph_store
    count = len(dependency_graph_store)
    dependency_graph_store.clear()
    logging.info(f"Cleared {count} dependency graphs from memory.")
    return {"message": f"Successfully cleared {count} dependency graphs from memory."}

