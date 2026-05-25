import json
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import SETTINGS_FILE
from app.models.agent import AppSettings, ProviderConfig

router = APIRouter()


def _load_settings() -> AppSettings:
    if SETTINGS_FILE.exists():
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return AppSettings(**data)
    return AppSettings()


def _save_settings(s: AppSettings):
    SETTINGS_FILE.write_text(s.model_dump_json(indent=2), encoding="utf-8")


def get_all_providers() -> list[ProviderConfig]:
    return _load_settings().providers


def get_provider(name: str) -> ProviderConfig:
    settings = _load_settings()
    for p in settings.providers:
        if p.name == name:
            return p
    raise HTTPException(404, f"Provider '{name}' not found")


@router.get("/providers")
async def list_providers():
    settings = _load_settings()
    return {
        "providers": [
            {
                "name": p.name,
                "provider_type": p.provider_type,
                "base_url": p.base_url,
                "models": p.models,
                "has_key": bool(p.api_key),
            }
            for p in settings.providers
        ],
        "default_provider": settings.default_provider,
    }


class ProviderInput(BaseModel):
    name: str
    provider_type: str
    api_key: str = ""
    base_url: str = ""
    models: list[str] = []


@router.post("/providers")
async def save_provider(inp: ProviderInput):
    settings = _load_settings()
    existing = [p for p in settings.providers if p.name != inp.name]
    existing.append(ProviderConfig(**inp.model_dump()))
    settings.providers = existing
    _save_settings(settings)
    return {"ok": True}


@router.delete("/providers/{name}")
async def delete_provider(name: str):
    settings = _load_settings()
    settings.providers = [p for p in settings.providers if p.name != name]
    _save_settings(settings)
    return {"ok": True}


class DefaultProviderInput(BaseModel):
    default_provider: str = ""


@router.post("/default-provider")
async def set_default_provider(inp: DefaultProviderInput):
    settings = _load_settings()
    if inp.default_provider:
        names = {p.name for p in settings.providers}
        if inp.default_provider not in names:
            raise HTTPException(404, f"Provider '{inp.default_provider}' not found")
    settings.default_provider = inp.default_provider
    _save_settings(settings)
    return {"ok": True, "default_provider": settings.default_provider}


@router.post("/import-ccswitch")
async def import_ccswitch():
    from app.memory.ccswitch import read_ccswitch_providers
    providers = read_ccswitch_providers()
    if not providers:
        raise HTTPException(404, "No providers found in CC Switch. Make sure CC Switch is installed and has configured providers.")

    settings = _load_settings()
    existing_names = {p.name for p in settings.providers}
    imported = 0
    for p in providers:
        if p["name"] not in existing_names:
            settings.providers.append(ProviderConfig(**p))
            imported += 1
    _save_settings(settings)
    return {"ok": True, "imported": imported}
