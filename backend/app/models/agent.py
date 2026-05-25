from pydantic import BaseModel, Field


class Lesson(BaseModel):
    game_id: str = ""
    role: str = ""
    won: bool = False
    reflection: str = ""
    key_moments: list[str] = Field(default_factory=list)
    player_count: int = 0
    role_config: str = ""
    rounds_played: int = 0
    survived_to_end: bool = False
    final_status: str = ""
    winner: str = ""
    useful_takeaways: list[str] = Field(default_factory=list)


class RoleMemorySummary(BaseModel):
    role: str = ""
    total_games: int = 0
    wins: int = 0
    losses: int = 0
    strengths: list[str] = Field(default_factory=list)
    pitfalls: list[str] = Field(default_factory=list)
    signals_to_watch: list[str] = Field(default_factory=list)
    role_tips: list[str] = Field(default_factory=list)
    recent_examples: list[str] = Field(default_factory=list)
    last_updated_game_id: str = ""


class RetrievedGameMemory(BaseModel):
    game_id: str = ""
    role: str = ""
    score: float = 0.0
    won: bool = False
    player_count: int = 0
    role_config: str = ""
    rounds_played: int = 0
    survived_to_end: bool = False
    final_status: str = ""
    winner: str = ""
    summary: str = ""
    key_moments: list[str] = Field(default_factory=list)
    useful_takeaways: list[str] = Field(default_factory=list)


class AgentMemory(BaseModel):
    agent_name: str
    personality: str = ""
    total_games: int = 0
    wins: int = 0
    losses: int = 0
    lessons: list[Lesson] = Field(default_factory=list)
    strategies: list[str] = Field(default_factory=list)
    role_summaries: dict[str, RoleMemorySummary] = Field(default_factory=dict)
    memory_version: int = 2


class ProviderConfig(BaseModel):
    name: str
    provider_type: str  # "claude" or "openai_compatible"
    api_key: str = ""
    base_url: str = ""
    models: list[str] = Field(default_factory=list)


class AppSettings(BaseModel):
    providers: list[ProviderConfig] = Field(default_factory=list)
    default_provider: str = ""
