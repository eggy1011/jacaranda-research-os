from __future__ import annotations

from dataclasses import dataclass

from jacaranda_api.market_data.models import CanonicalMetric, CanonicalSource, SourceDraft


@dataclass(frozen=True, slots=True)
class SourceRegistration:
    registry: SourceRegistry
    source: CanonicalSource


@dataclass(frozen=True, slots=True)
class SourceRegistry:
    """Persistent package-local source registry; registration never mutates an existing value."""

    sources: tuple[CanonicalSource, ...] = ()

    def __post_init__(self) -> None:
        ids = [source.source_id for source in self.sources]
        identities = [source.identity for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source identifiers must be unique")
        if len(identities) != len(set(identities)):
            raise ValueError("source identities must be unique")

    def register(self, draft: SourceDraft) -> SourceRegistration:
        for source in self.sources:
            if source.identity == draft.identity:
                return SourceRegistration(registry=self, source=source)

        next_index = (
            max((int(source.source_id.removeprefix("SRC-")) for source in self.sources), default=0)
            + 1
        )
        if next_index > 999:
            raise ValueError("source identifier sequence exhausted")
        source = draft.with_id(f"SRC-{next_index:03d}")
        return SourceRegistration(
            registry=SourceRegistry(sources=(*self.sources, source)),
            source=source,
        )

    def resolve(self, source_id: str) -> CanonicalSource:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        raise KeyError(source_id)

    def contains(self, source_id: str) -> bool:
        return any(source.source_id == source_id for source in self.sources)

    def assert_resolves(self, metrics: tuple[CanonicalMetric, ...]) -> None:
        unresolved = sorted(
            {metric.source_id for metric in metrics if not self.contains(metric.source_id)}
        )
        if unresolved:
            raise ValueError(f"unresolved source references: {', '.join(unresolved)}")

    def as_research_sources(self) -> list[dict[str, object]]:
        return [
            source.model_dump(mode="json", by_alias=True, exclude_none=True)
            for source in self.sources
        ]
