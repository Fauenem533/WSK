import asyncio
import logging
import os

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.database import init_db, get_db, SessionLocal
from app.routers.auth_router import router as auth_router
from app.routers.races_router import router as races_router
from app.scrapers.scraper import scrape_all
from app.config import SCRAPE_INTERVAL_HOURS
from app.auth import require_user
from app.models import User, ScrapeLog

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def scheduled_scrape():
    """Background job: scrape all races."""
    logger.info("Starting scheduled scrape...")
    db = SessionLocal()
    try:
        results = await scrape_all(db)
        logger.info(f"Scrape complete: {results}")
    except Exception as e:
        logger.error(f"Scheduled scrape failed: {e}", exc_info=True)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    logger.info("Database initialized")

    # Check if DB is empty -> initial scrape
    db = SessionLocal()
    from app.models import Result
    count = db.query(Result).count()
    db.close()

    if count == 0:
        logger.info("Empty database, running initial scrape...")
        asyncio.create_task(scheduled_scrape())

    # Schedule periodic scraping
    scheduler.add_job(
        scheduled_scrape, "interval",
        hours=SCRAPE_INTERVAL_HOURS,
        id="scrape_all",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started (every {SCRAPE_INTERVAL_HOURS}h)")

    yield

    # Shutdown
    scheduler.shutdown()


app = FastAPI(
    title="WSK Tracker API",
    description="Wielki Szlem Komandosa - API wyników biegów",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - allow all origins (frontend served from same domain, but just in case)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(races_router)

# Static files (frontend)
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
elif os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    for path in [os.path.join(static_dir, "index.html"), "static/index.html"]:
        if os.path.isfile(path):
            return FileResponse(path)
    return {"message": "WSK Tracker API is running. Frontend not found."}


# Admin endpoint: trigger manual scrape
@app.post("/api/admin/scrape")
async def trigger_scrape(db: Session = Depends(get_db)):
    results = await scrape_all(db)
    return {"results": results}


# Scrape status
@app.get("/api/admin/scrape-status")
async def scrape_status(db: Session = Depends(get_db)):
    logs = db.query(ScrapeLog).order_by(ScrapeLog.scraped_at.desc()).limit(20).all()
    return [
        {
            "race_id": l.race_id,
            "status": l.status,
            "runners_count": l.runners_count,
            "message": l.message,
            "scraped_at": l.scraped_at.isoformat(),
        }
        for l in logs
    ]
