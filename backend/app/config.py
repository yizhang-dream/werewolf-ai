from pathlib import Path
from pydantic_settings import BaseSettings

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AGENTS_DIR = DATA_DIR / "agents"
GAMES_DIR = DATA_DIR / "games"
SETTINGS_FILE = DATA_DIR / "settings.json"


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = {"env_prefix": "WEREWOLF_"}

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
