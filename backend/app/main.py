from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import AGENTS_DIR, GAMES_DIR, SETTINGS_FILE, settings
from app.routers import agents, events, game, settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text("{}", encoding="utf-8")
    yield


app = FastAPI(title="AI Werewolf", version="0.1.0", lifespan=lifespan)

cors_origins = settings.parsed_cors_origins
allow_all_origins = "*" in cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else cors_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(game.router, prefix="/api/games", tags=["game"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(events.router, prefix="/api/events", tags=["events"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
