"""Pipeline result and metrics domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PipelineMetrics:
    """Aggregated token and timing metrics for one pipeline run."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    transcript_seconds: float = 0.0
    generation_seconds: float = 0.0

    def add_from(self, other: PipelineMetrics) -> None:
        """Accumulate another metrics snapshot into this instance."""
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.cost_usd += other.cost_usd
        self.transcript_seconds += other.transcript_seconds
        self.generation_seconds += other.generation_seconds

    def copy(self) -> PipelineMetrics:
        """Return an immutable snapshot copy."""
        return PipelineMetrics(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
            cost_usd=self.cost_usd,
            transcript_seconds=self.transcript_seconds,
            generation_seconds=self.generation_seconds,
        )


@dataclass
class PipelineResult:
    """Result of pipeline execution."""

    success_count: int
    failure_count: int
    total_count: int
    video_ids: list[str]
    errors: dict[str, str]
    metrics: PipelineMetrics = field(default_factory=PipelineMetrics)
