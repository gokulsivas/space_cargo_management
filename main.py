from fastapi import FastAPI
from routers import import_export, placement, search_retrieve, waste, time_simulation, logs

app = FastAPI(
    title="Cargo Management API",
    description="API for managing cargo placement, retrieval, waste, and time simulation.",
    version="1.0.0"
)

app.include_router(import_export.router)
app.include_router(logs.router)
app.include_router(placement.router)
app.include_router(search_retrieve.router)
app.include_router(waste.router)
app.include_router(time_simulation.router)


# Root endpoint
@app.get("/")
async def root():
    return {"message": "Cargo Management API is running!"}