"""Nahj AI — FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import get_settings
from app.rag.retriever import Retriever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("nahj-ai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting Nahj AI (LLM: %s @ %s)", settings.llm_model, settings.llm_base_url)
    app.state.retriever = Retriever(settings)
    if app.state.retriever.chunk_count == 0:
        logger.warning(
            "Index is empty. Run:  python scripts/download_data.py && "
            "python scripts/scrape_alislam.py && python scripts/build_corpus.py "
            "&& python scripts/ingest.py"
        )
    yield


app = FastAPI(
    title="Nahj AI",
    description="AI chatbot grounded in Nahjul Balagha — the sermons, letters "
    "and sayings of Imam Ali ibn Abi Talib (peace be upon him).",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Serve the chat frontend at /
app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
