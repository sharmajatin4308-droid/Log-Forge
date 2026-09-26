from pydantic import BaseModel


class PipelineStats(BaseModel):
    total: int = 0
    success: int = 0
    partial: int = 0
    failed: int = 0
    total_duration_ms: float = 0.0

    @property
    def eps(self) -> float:
        if self.total <= 0 or self.total_duration_ms <= 0:
            return 0.0
        return self.total / (self.total_duration_ms / 1000.0)

    @property
    def success_rate(self) -> float:
        return self.success / self.total if self.total > 0 else 0.0
