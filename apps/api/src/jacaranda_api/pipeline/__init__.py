"""Research pipeline: stage orchestration, checkpoints, validation and artifacts.

Currently ships the offline fixture-only (mock) wiring; the real-provider wiring
is added in the productisation phases and shares this module's orchestration.
"""

from jacaranda_api.pipeline.orchestrator import MockResearchOrchestrator

__all__ = ["MockResearchOrchestrator"]
