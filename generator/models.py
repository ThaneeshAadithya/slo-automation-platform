"""
Data models for SLO definitions.
Parsed from YAML, used by all generators.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MetricConfig:
    good_query: str
    total_query: str
    latency_threshold_ms: Optional[float] = None


@dataclass
class AlertingConfig:
    page_on_burn: bool = True
    ticket_on_budget_low: bool = True
    budget_low_threshold: float = 0.10


@dataclass
class Annotations:
    runbook_url: str = ""
    dashboard_url: str = ""


@dataclass
class SLODefinition:
    name: str
    slo_type: str          # availability | latency | error_rate | throughput
    target: float          # e.g. 0.999
    window: str            # e.g. "30d"
    description: str = ""
    metric: Optional[MetricConfig] = None
    alerting: AlertingConfig = field(default_factory=AlertingConfig)
    annotations: Annotations = field(default_factory=Annotations)

    @property
    def error_rate(self) -> float:
        """Error budget = 1 - target."""
        return 1 - self.target

    @property
    def target_pct(self) -> str:
        return f"{self.target * 100:.3f}%"

    @property
    def slo_id(self) -> str:
        """Unique identifier for Prometheus metric names."""
        return self.name.lower().replace(" ", "_").replace("-", "_")


@dataclass
class ServiceSLO:
    service: str
    team: str
    namespace: str
    slos: list[SLODefinition]
    labels: dict = field(default_factory=dict)

    @property
    def service_id(self) -> str:
        return self.service.lower().replace("-", "_")
