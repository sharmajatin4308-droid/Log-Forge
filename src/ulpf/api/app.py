from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .routes.events import router as events_router
from .routes.extensions import router as extensions_router
from .routes.health import router as health_router
from .routes.ingest import router as ingest_router

app = FastAPI(
    title="LogForge",
    description="Universal Security Log Pre-processing & Normalization Framework",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files mounting
static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routers under /api
app.include_router(health_router, prefix="/api")
app.include_router(extensions_router, prefix="/api")
app.include_router(ingest_router, prefix="/api")
app.include_router(events_router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
async def root():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>LogForge API is running. UI not found.</h1>")
