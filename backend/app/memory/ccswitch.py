"""Read provider configs from CC Switch's SQLite database."""
import json
import logging
import shutil
import sqlite3
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

CC_SWITCH_DB = Path.home() / ".cc-switch" / "cc-switch.db"


def read_ccswitch_providers() -> list[dict]:
    """Read provider configs from CC Switch SQLite DB. Returns list of provider dicts."""
    if not CC_SWITCH_DB.exists():
        logger.info("CC Switch database not found at %s", CC_SWITCH_DB)
        return []

    # Copy to temp file to avoid locking issues (CC Switch holds the DB open)
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        shutil.copy2(str(CC_SWITCH_DB), tmp.name)
    except Exception as e:
        logger.warning("Failed to copy CC Switch DB: %s", e)
        return []

    results = []
    try:
        conn = sqlite3.connect(tmp.name)
        cursor = conn.cursor()
        cursor.execute("SELECT name, settings_config, app_type, meta FROM providers")
        for name, config_str, app_type, meta_str in cursor.fetchall():
            try:
                config = json.loads(config_str) if config_str else {}
                meta = json.loads(meta_str) if meta_str else {}
                env = config.get("env", {})
                api_key = env.get("ANTHROPIC_AUTH_TOKEN", env.get("OPENAI_API_KEY", ""))
                base_url = env.get("ANTHROPIC_BASE_URL", env.get("OPENAI_BASE_URL", ""))
                api_format = meta.get("apiFormat", "")

                if not api_key:
                    continue

                models = []
                for key in ["ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL"]:
                    m = env.get(key, "")
                    if m and m not in models:
                        models.append(m)

                provider = {
                    "name": name,
                    "provider_type": _map_provider_type(app_type, api_format),
                    "api_key": api_key,
                    "base_url": base_url,
                    "models": models,
                }
                results.append(provider)
            except Exception as e:
                logger.warning("Failed to parse provider %s: %s", name, e)
        conn.close()
    except Exception as e:
        logger.warning("Failed to read CC Switch DB: %s", e)
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    return results


def _map_provider_type(app_type: str, api_format: str) -> str:
    if api_format == "anthropic" or app_type == "claude":
        return "claude"
    return "openai_compatible"
