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
    "itemId": pl.Utf8,
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
            itemId = row["itemId"]
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
    required_columns = {"containerId", "zone", "width", "depth", "height"}

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
                "containerId": row["containerId"],
                "zone": row["zone"],
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
        result = cargo_system.optimize_placement()
        log_action("Optimize Placement", "Cargo placement optimization executed.")

        print("=== Raw Optimization Result ===")
        print(result)

        # Ensure 'placements' exists and is a valid DataFrame
        placements = None
        if isinstance(result, pl.DataFrame) and "placements" in result.columns:
            placements = result["placements"][0] if not result["placements"].is_null()[0] else None

        print("=== Extracted Placements ===")
        print(placements)

        if placements is None or placements.is_empty():
            log_action("Export Failed", "No placements available for export.")
            raise HTTPException(status_code=404, detail="No placements available.")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Item ID", "Zone", "Coordinates (W1,D1,H1),(W2,D2,H2)"])

        for placement in placements.iter_rows(named=True):
            writer.writerow([
                placement["itemId"],
                placement["zone"],  # Use zone instead of containerId
                f"({placement['start_x']},{placement['start_y']},{placement['start_z']}),"
                f"({placement['end_x']},{placement['end_y']},{placement['end_z']})"
            ])

        output.seek(0)
        log_action("Export Arrangement", "Exported cargo arrangement successfully.")

        return Response(output.getvalue(), media_type="text/csv", headers={
            "Content-Disposition": "attachment; filename=arrangement.csv"
        })
    except Exception as e:
        log_action("Export Failed", f"Error exporting arrangement: {str(e)}")
        print(f"Export Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error exporting arrangement: {str(e)}")
