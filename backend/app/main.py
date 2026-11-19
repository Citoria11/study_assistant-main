import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database.session import init_db
from app.rag import init_rag
from app.routes import agent, mnemonics, auth, notebook, games, books
from app.routes import user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_rag()
    yield


app = FastAPI(
    title="Study Assistant API",
    description="Backend API for the Study Assistant chatbot powered by LangGraph.",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS – allow the React dev server and any configured frontend origin
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://frontend:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(mnemonics.router, prefix="/api/mnemonics", tags=["mnemonics"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(notebook.router, prefix="/api/notebook", tags=["notebook"])
app.include_router(games.router, prefix="/api/games", tags=["games"])
app.include_router(books.router, prefix="/api/books", tags=["books"])
app.include_router(user.router, prefix="/api/user", tags=["user"])


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}
