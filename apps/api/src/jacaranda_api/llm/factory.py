from __future__ import annotations

from jacaranda_api.config import Settings
from jacaranda_api.llm.catalog import PromptCatalogReader
from jacaranda_api.llm.contracts import LLMProvider
from jacaranda_api.llm.http_client import OpenRouterHTTPClient
from jacaranda_api.llm.openrouter import OpenRouterLLMProvider
from jacaranda_api.llm.rotation import RotatingOpenRouterProvider


def candidate_models(settings: Settings) -> list[str]:
    models = [item.strip() for item in settings.openrouter_models.split(",") if item.strip()]
    return models or [settings.openrouter_model]


def build_llm_provider(
    settings: Settings,
    catalog: PromptCatalogReader,
    http_client: OpenRouterHTTPClient,
) -> LLMProvider:
    """Build the configured provider; a multi-candidate list gets rotation (D-008).

    Model policy is enforced per candidate by the OpenRouterLLMProvider
    constructor, so a paid model without the explicit opt-in fails here at
    configuration time, never mid-run.
    """
    providers = [
        (
            model,
            OpenRouterLLMProvider(
                api_key=settings.openrouter_api_key,
                requested_model=model,
                catalog=catalog,
                http_client=http_client,
                max_attempts=settings.llm_max_attempts,
                allow_paid_model=settings.allow_paid_models,
            ),
        )
        for model in candidate_models(settings)
    ]
    if len(providers) == 1:
        return providers[0][1]
    return RotatingOpenRouterProvider(providers)
