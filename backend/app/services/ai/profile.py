import json
import logging

from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.data_source import BusinessProfile
from app.services.ai.groq_provider import GroqProvider

logger = logging.getLogger(__name__)
MAX_CONTEXT_BYTES = 80_000


def profile_context(source) -> str:
    tables = []
    for table in source.tables:
        tables.append({
            "schema": table.schema_name,
            "table": table.name,
            "table_type": table.table_type,
            "foreign_keys": table.foreign_keys,
            "columns": [{"name": column.name, "type": column.data_type, "nullable": column.nullable,
                         "primary_key": column.is_primary_key, "foreign_key": column.foreign_key,
                         "safe_profile": column.profile} for column in table.columns],
        })
    result = json.dumps({"metadata_only": True, "tables": tables}, ensure_ascii=True)
    if len(result.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError("Schema exceeds the safe AI context size limit")
    return result


def generate_business_profile(source) -> tuple[str, BusinessProfile | None, str | None]:
    settings = get_settings()
    if settings.ai_provider != "groq":
        return "not_configured", None, "Configured AI provider is not supported"
    if not settings.groq_api_key.get_secret_value():
        return "not_configured", None, "AI provider is not configured; metadata discovery is still available"
    try:
        raw = GroqProvider().generate_structured_profile(profile_context(source))
        profile = BusinessProfile.model_validate_json(raw)
        return "available", profile, None
    except (ValidationError, ValueError):
        logger.warning("Business profile response was invalid or exceeded the context policy")
        return "failed", None, "The business profile could not be validated. Retry discovery or check provider configuration."
    except Exception:
        logger.warning("Business profile provider request failed")
        return "failed", None, "The AI provider could not generate a profile. Metadata discovery remains available."
