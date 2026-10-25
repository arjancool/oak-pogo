"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.analysis import (
    AnalysisRun,
    BattleTeam,
    BattleTeamMember,
    PokemonAnalysis,
    PvpRanking,
)
from app.models.base import Base
from app.models.gamedata import AppSetting, GameDataVersion, GameEvent
from app.models.identity import AuditLog, User, UserSession
from app.models.imports import BackgroundJob, ImportIssue, ImportJob, SyncRun
from app.models.pokemon import PlannedAction, Pokemon, PokemonChangeEvent, PokemonUserMetadata
from app.models.trainer import (
    InventorySnapshot,
    ItemInventory,
    ManualResource,
    TagLabel,
    TrainerAccount,
    WebhookCredential,
)

__all__ = [
    "AnalysisRun",
    "AppSetting",
    "AuditLog",
    "BackgroundJob",
    "Base",
    "BattleTeam",
    "BattleTeamMember",
    "GameDataVersion",
    "GameEvent",
    "ImportIssue",
    "ImportJob",
    "InventorySnapshot",
    "ItemInventory",
    "ManualResource",
    "PlannedAction",
    "Pokemon",
    "PokemonAnalysis",
    "PokemonChangeEvent",
    "PokemonUserMetadata",
    "PvpRanking",
    "SyncRun",
    "TagLabel",
    "TrainerAccount",
    "User",
    "UserSession",
    "WebhookCredential",
]
