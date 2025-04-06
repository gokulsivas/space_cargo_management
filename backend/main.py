from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import items, containers, placement, search, time_simulation, container3d, container

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(items.router, prefix="/api", tags=["items"])
app.include_router(containers.router, prefix="/api", tags=["containers"])
app.include_router(placement.router, prefix="/api", tags=["placement"])
app.include_router(search.router, prefix="/api", tags=["search"])
app.include_router(time_simulation.router, prefix="/api", tags=["time_simulation"])
app.include_router(container3d.router, prefix="/api", tags=["container3d"])
app.include_router(container.router, prefix="/api", tags=["container"])

@app.get("/")
async def root():
    return {"message": "Welcome to Space Hack API"} 