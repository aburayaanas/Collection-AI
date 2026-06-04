from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.narrative_service import router as narrative_router
from src.database.connection import db

app = FastAPI(
    title="Collection AI - Real-Time Narrative Service",
    description="Lazy-loading LLM narrative generation service for bank collection officers.",
    version="1.0.0"
)

# Enable CORS to allow the frontend to fetch resources
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register the router
app.include_router(narrative_router, tags=["Narratives"])

@app.on_event("startup")
def startup_event():
    # Initialize the database connection pool
    db.initialize_pool()

@app.on_event("shutdown")
def shutdown_event():
    # Close the database connection pool
    db.close_pool()

@app.get("/")
def read_root():
    return {"message": "Collection AI Narrative API is running."}
