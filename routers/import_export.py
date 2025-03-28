import csv
import io
from fastapi import APIRouter, HTTPException, UploadFile, File, Response
from schemas import CargoPlacementSystem
import polars as pl

router = APIRouter(
    prefix="/api",
    tags=["import-export"]
)

cargo_system = CargoPlacementSystem()


### **1. Import Items from CSV**
@router.post("/import/items")
async def import_items(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")

    contents = await file.read()
    decoded_contents = contents.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded_contents))

    items = []
    errors = []
    
    for row_number, row in enumerate(reader, start=1):
        try:
            items.append({
                "itemId": row["itemId"],
                "name": row["name"],
                "width": float(row["width"]),
                "depth": float(row["depth"]),
                "height": float(row["height"]),
                "priority": int(row["priority"]),
                "preferredZone": row["preferredZone"]
            })
        except (ValueError, KeyError) as e:
            errors.append({"row": row_number, "message": str(e)})

    if items:
        cargo_system.add_items(items)

    return {
        "success": len(errors) == 0,
        "itemsImported": len(items),
        "errors": errors
    }


### **2. Import Containers from CSV**
@router.post("/import/containers")
async def import_containers(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")

    contents = await file.read()
    decoded_contents = contents.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded_contents))

    containers = []
    errors = []
    
    for row_number, row in enumerate(reader, start=1):
        try:
            containers.append({
                "containerId": row["containerId"],
                "width": float(row["width"]),
                "depth": float(row["depth"]),
                "height": float(row["height"])
            })
        except (ValueError, KeyError) as e:
            errors.append({"row": row_number, "message": str(e)})

    if containers:
        cargo_system.add_containers(containers)

    return {
        "success": len(errors) == 0,
        "containersImported": len(containers),
        "errors": errors
    }


### **3. Export Cargo Arrangement as CSV**
@router.get("/export/arrangement")
async def export_arrangement():
    placements = cargo_system.optimize_placement()["placements"]

    if not placements:
        raise HTTPException(status_code=404, detail="No placements available.")

    output = io.StringIO()
    writer = csv.writer(output)

    # CSV Header
    writer.writerow(["Item ID", "Container ID", "Start Coordinates (W,D,H)", "End Coordinates (W,D,H)"])

    # CSV Rows
    for placement in placements:
        start = placement["position"]["startCoordinates"]
        end = placement["position"]["endCoordinates"]
        writer.writerow([
            placement["itemId"],
            placement["containerId"],
            f"({start['width']},{start['depth']},{start['height']})",
            f"({end['width']},{end['depth']},{end['height']})"
        ])

    output.seek(0)
    return Response(output.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=arrangement.csv"
    })
