"""
Load and validate SLO definitions from YAML files.
Validates against JSON Schema before returning parsed models.
"""
import json
import logging
from pathlib import Path
from typing import Generator

import jsonschema
import yaml

from .models import (
    AlertingConfig, Annotations, MetricConfig, SLODefinition, ServiceSLO
)

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent.parent / "slos" / "schemas" / "slo-schema.json"
SLOS_DIR    = Path(__file__).parent.parent / "slos" / "services"


def load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def load_service_slo(yaml_path: Path) -> ServiceSLO:
    """Load and validate a single SLO YAML file."""
    with open(yaml_path) as f:
        raw = yaml.safe_load(f)

    # Validate against JSON Schema
    schema = load_schema()
    try:
        jsonschema.validate(instance=raw, schema=schema)
    except jsonschema.ValidationError as e:
        raise ValueError(f"SLO validation failed for {yaml_path.name}: {e.message}") from e

    slos = []
    for slo_raw in raw["slos"]:
        metric = None
        if "metric" in slo_raw:
            m = slo_raw["metric"]
            metric = MetricConfig(
                good_query=m["good_query"].strip(),
                total_query=m["total_query"].strip(),
                latency_threshold_ms=m.get("latency_threshold_ms"),
            )

        alerting_raw = slo_raw.get("alerting", {})
        alerting = AlertingConfig(
            page_on_burn=alerting_raw.get("page_on_burn", True),
            ticket_on_budget_low=alerting_raw.get("ticket_on_budget_low", True),
            budget_low_threshold=alerting_raw.get("budget_low_threshold", 0.10),
        )

        ann_raw = slo_raw.get("annotations", {})
        annotations = Annotations(
            runbook_url=ann_raw.get("runbook_url", ""),
            dashboard_url=ann_raw.get("dashboard_url", ""),
        )

        slos.append(SLODefinition(
            name=slo_raw["name"],
            slo_type=slo_raw["type"],
            target=slo_raw["target"],
            window=slo_raw["window"],
            description=slo_raw.get("description", ""),
            metric=metric,
            alerting=alerting,
            annotations=annotations,
        ))

    return ServiceSLO(
        service=raw["service"],
        team=raw["team"],
        namespace=raw.get("namespace", "default"),
        labels=raw.get("labels", {}),
        slos=slos,
    )


def load_all_slos() -> Generator[ServiceSLO, None, None]:
    """Load all SLO definitions from the slos/services/ directory."""
    for yaml_path in sorted(SLOS_DIR.glob("*.yaml")):
        logger.info("Loading SLO definition: %s", yaml_path.name)
        yield load_service_slo(yaml_path)
