import csv
import io
import polars as pl
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, UploadFile, File, Response
from schemas import CargoPlacementSystem, ImportItemsResponse, ImportContainersResponse, CargoArrangementExport, Coordinates
import polars as pl
import json

router = APIRouter(
    prefix="/api",
    tags=["import-export"]
)

cargo_system = CargoPlacementSystem()

LOG_FILE = "logs.csv"

# DataFrame to store logs
log_columns = ["timestamp", "userId", "actionType", "itemId", "details"]
logs_df = pl.DataFrame(schema={
    "timestamp": pl.Utf8,
    "userId": pl.Utf8,
    "actionType": pl.Utf8,
    "itemId": pl.Int64, # TO integer
    "details": pl.Utf8  # Store details as a string (JSON)
})


def log_action(actionType: str, details: dict = None, userId: str = "", itemId: str = ""):
    global logs_df

    if not isinstance(details, dict):  # Ensure details is a dictionary
        details = {"fromContainer": "", "toContainer": "", "reason": str(details)}

    structured_details = {
        "fromContainer": details.get("fromContainer", ""),
        "toContainer": details.get("toContainer", ""),
        "reason": details.get("reason", "")
    }

    details_json = json.dumps(structured_details)  # Store as JSON string

    new_entry = pl.DataFrame(
        {
            "timestamp": [datetime.now(timezone.utc).isoformat()],
            "userId": [userId],
            "actionType": [actionType],
            "itemId": [itemId],
            "details": [details_json],  # Ensure JSON format
        }
    )

    logs_df = pl.concat([logs_df, new_entry], how="vertical")
    logs_df.write_csv(LOG_FILE)



def convert_csv_to_json(file_contents: str):
    """ Convert CSV data to a list of dictionaries (JSON format). """
    reader = csv.DictReader(io.StringIO(file_contents))
    return [row for row in reader]

### **1. Import Items from CSV**
@router.post("/import/items", response_model=ImportItemsResponse)
async def import_items(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")

    try:
        contents = await file.read()
        decoded_contents = contents.decode("utf-8").strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")

    if not decoded_contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Validate required columns
    reader = csv.DictReader(io.StringIO(decoded_contents))
    required_columns = {"itemId", "name", "width", "depth", "height", "mass", "priority", "expiryDate", "usageLimit", "preferredZone"}

    if not required_columns.issubset(set(reader.fieldnames or [])):
        missing_columns = required_columns - set(reader.fieldnames or [])
        raise HTTPException(status_code=400, detail=f"Missing required columns: {missing_columns}")

    # Convert CSV to JSON
    items_json = convert_csv_to_json(decoded_contents)

    items = []
    errors = []

    for row_number, row in enumerate(items_json, start=1):
        try:
            # Convert and validate required fields
            itemId = int(row["itemId"])
            width = float(row["width"])
            depth = float(row["depth"])
            height = float(row["height"])
            mass = float(row["mass"])
            priority_value = int(row["priority"])
            preferredZone = row["preferredZone"]
            name = row["name"]

            if not (1 <= priority_value <= 100):
                raise ValueError("Priority must be between 1 and 100.")

            # Handle expiry date conversion safely
            expiryDate = None
            expiry_date_value = row["expiryDate"].strip().lower()
            if expiry_date_value not in {"n/a", ""}:
                try:
                    expiryDate = expiry_date_value
                except ValueError:
                    raise ValueError(f"Invalid date format '{expiry_date_value}'. Use YYYY-MM-DD.")

            # Convert usage limit safely
            usage_limit_value = row["usageLimit"].split()[0] if " " in row["usageLimit"] else row["usageLimit"]
            usageLimit = int(usage_limit_value) if usage_limit_value.isdigit() else 0

            # Create item as dictionary matching the expected format
            item = {
                "itemId": itemId,
                "name": name,
                "width": width,
                "depth": depth,
                "height": height,
                "mass": mass,
                "priority": priority_value,
                "expiryDate": expiryDate,
                "usageLimit": usageLimit,
                "preferredZone": preferredZone
            }

            items.append(item)

        except (ValueError, KeyError) as e:
            errors.append({"row": row_number, "message": str(e)})

    if items:
        try:
            cargo_system.add_items(items)
            log_action("Import Items", f"Imported {len(items)} items successfully.")
            
            # Create imported_items.csv file
            items_df = pl.DataFrame(items)
            items_df.write_csv("imported_items.csv")
            
        except Exception as e:
            log_action("Import Items Failed", f"Error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing items: {str(e)}")

    return ImportItemsResponse(
        success=len(errors) == 0,
        itemsImported=len(items),
        errors=errors,
        message="Items imported successfully" if len(errors) == 0 else "Some items could not be imported"
    )


### **2. Import Containers from CSV**
@router.post("/import/containers", response_model=ImportContainersResponse)
async def import_containers(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")

    try:
        contents = await file.read()
        decoded_contents = contents.decode("utf-8").strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")

    if not decoded_contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Validate required columns
    reader = csv.DictReader(io.StringIO(decoded_contents))
    required_columns = {"zone", "containerId", "width", "depth", "height"}

    if not required_columns.issubset(set(reader.fieldnames or [])):
        missing_columns = required_columns - set(reader.fieldnames or [])
        raise HTTPException(status_code=400, detail=f"Missing required columns: {missing_columns}")

    # Convert CSV to JSON
    containers_json = convert_csv_to_json(decoded_contents)

    containers = []
    errors = []

    for row_number, row in enumerate(containers_json, start=1):
        try:
            container = {
                "zone": row["zone"],
                "containerId": row["containerId"],
                "width": float(row["width"]),
                "depth": float(row["depth"]),
                "height": float(row["height"])
            }

            containers.append(container)

        except (ValueError, KeyError) as e:
            errors.append({"row": row_number, "message": str(e)})

    if containers:
        try:
            cargo_system.add_containers(containers)
            log_action("Import Containers", f"Imported {len(containers)} containers successfully.")
            
            # Create imported_containers.csv file
            containers_df = pl.DataFrame(containers)
            containers_df.write_csv("imported_containers.csv")
            
        except Exception as e:
            log_action("Import Containers Failed", f"Error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing containers: {str(e)}")


    return ImportContainersResponse(
        success=len(errors) == 0,
        containersImported=len(containers),
        errors=errors,
        message="Containers imported successfully" if len(errors) == 0 else "Some containers could not be imported"
    )

### **3. Export Cargo Arrangement as CSV**
@router.get("/export/arrangement")
async def export_arrangement():
    try:
        print("\n=== Starting Export Process ===")
        
        # Verify data is loaded
        if cargo_system.items_df.is_empty():
            print("Error: No items loaded")
            raise HTTPException(status_code=400, detail="No items loaded")
            
        if cargo_system.containers_df.is_empty():
            print("Error: No containers loaded")
            raise HTTPException(status_code=400, detail="No containers loaded")
            
        total_items = len(cargo_system.items_df)
        print(f"Total items to process: {total_items}")
        
        # Create direct placements without octree
        placements = []
        current_position = {"x": 0, "y": 0, "z": 0}
        
        # Process each item and assign to its preferred zone
        for item in cargo_system.items_df.iter_rows(named=True):
            try:
                # Get container dimensions for the preferred zone
                container = cargo_system.containers_df.filter(
                    pl.col("zone") == item["preferredZone"]
                ).row(0, named=True)
                
                # Calculate item placement
                placement = {
                    "itemId": item["itemId"],
                    "zone": item["preferredZone"],
                    "start_x": current_position["x"],
                    "start_y": current_position["y"],
                    "start_z": current_position["z"],
                    "end_x": current_position["x"] + item["width"],
                    "end_y": current_position["y"] + item["depth"],
                    "end_z": current_position["z"] + item["height"]
                }
                
                # Update position for next item (simple stacking)
                if current_position["x"] + item["width"] * 2 <= float(container["width"]):
                    current_position["x"] += item["width"]
                else:
                    current_position["x"] = 0
                    if current_position["y"] + item["depth"] * 2 <= float(container["depth"]):
                        current_position["y"] += item["depth"]
                    else:
                        current_position["y"] = 0
                        current_position["z"] += item["height"]
                
                placements.append(placement)
                
            except Exception as e:
                print(f"Error processing item {item['itemId']}: {str(e)}")
                continue
        
        # Create and save the cargo_arrangement.csv file
        arrangement_csv_path = "cargo_arrangement.csv"
        
        with open(arrangement_csv_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["itemId", "zone", "coordinates"])
            
            for placement in placements:
                writer.writerow([
                    placement["itemId"],
                    placement["zone"],
                    f"({placement['start_x']},{placement['start_y']},{placement['start_z']}),"
                    f"({placement['end_x']},{placement['end_y']},{placement['end_z']})"
                ])
        
        print(f"Wrote {len(placements)} placements to {arrangement_csv_path}")
        
        # Prepare the response
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["itemId", "zone", "coordinates"])
        
        with open(arrangement_csv_path, 'r') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # Skip header
            for row in reader:
                writer.writerow(row)
                
        output.seek(0)
        
        print("=== Export Process Complete ===")
        log_action("Export Arrangement", f"Exported {len(placements)} placements successfully")

        return Response(
            output.getvalue(), 
            media_type="text/csv", 
            headers={
                "Content-Disposition": "attachment; filename=arrangement.csv"
            }
        )
        
    except Exception as e:
        print(f"Export Error: {str(e)}")
        import traceback
        print(traceback.format_exc())
        log_action("Export Failed", f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))