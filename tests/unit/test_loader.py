"""Unit tests for SLO YAML loader and validator."""
import tempfile
from pathlib import Path

import pytest
import yaml

from generator.loader import load_service_slo
from generator.models import SLODefinition, ServiceSLO


VALID_SLO_YAML = """
service: test-service
team: platform
namespace: backend
slos:
  - name: availability
    type: availability
    target: 0.999
    window: 30d
    metric:
      good_query: 'sum(rate(http_requests_total{status!~"5.."}[{{.window}}]))'
      total_query: 'sum(rate(http_requests_total[{{.window}}]))'
    alerting:
      page_on_burn: true
      budget_low_threshold: 0.10
    annotations:
      runbook_url: https://runbooks.example.com/test
"""


def write_tmp_yaml(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


class TestLoader:
    def test_loads_valid_yaml(self):
        path = write_tmp_yaml(VALID_SLO_YAML)
        service = load_service_slo(path)
        assert service.service == "test-service"
        assert service.team == "platform"
        assert len(service.slos) == 1

    def test_slo_fields_correctly_parsed(self):
        path = write_tmp_yaml(VALID_SLO_YAML)
        service = load_service_slo(path)
        slo = service.slos[0]
        assert slo.name == "availability"
        assert slo.slo_type == "availability"
        assert slo.target == 0.999
        assert slo.window == "30d"

    def test_metric_config_parsed(self):
        path = write_tmp_yaml(VALID_SLO_YAML)
        service = load_service_slo(path)
        assert service.slos[0].metric is not None
        assert "http_requests_total" in service.slos[0].metric.good_query

    def test_alerting_config_parsed(self):
        path = write_tmp_yaml(VALID_SLO_YAML)
        service = load_service_slo(path)
        alerting = service.slos[0].alerting
        assert alerting.page_on_burn is True
        assert alerting.budget_low_threshold == 0.10

    def test_annotations_parsed(self):
        path = write_tmp_yaml(VALID_SLO_YAML)
        service = load_service_slo(path)
        assert "runbooks.example.com" in service.slos[0].annotations.runbook_url

    def test_rejects_invalid_target_above_1(self):
        bad_yaml = VALID_SLO_YAML.replace("target: 0.999", "target: 1.5")
        path = write_tmp_yaml(bad_yaml)
        with pytest.raises(ValueError, match="SLO validation failed"):
            load_service_slo(path)

    def test_rejects_missing_required_field(self):
        bad_yaml = """
service: test-service
team: platform
slos:
  - name: test
    type: availability
    window: 30d
    # Missing target
"""
        path = write_tmp_yaml(bad_yaml)
        with pytest.raises(ValueError):
            load_service_slo(path)

    def test_rejects_invalid_slo_type(self):
        bad_yaml = VALID_SLO_YAML.replace("type: availability", "type: invalid_type")
        path = write_tmp_yaml(bad_yaml)
        with pytest.raises(ValueError):
            load_service_slo(path)

    def test_rejects_invalid_window(self):
        bad_yaml = VALID_SLO_YAML.replace("window: 30d", "window: 15d")
        path = write_tmp_yaml(bad_yaml)
        with pytest.raises(ValueError):
            load_service_slo(path)

    def test_multiple_slos(self):
        multi_yaml = VALID_SLO_YAML + """
  - name: latency-p99
    type: latency
    target: 0.95
    window: 30d
    metric:
      good_query: 'sum(rate(http_request_duration_seconds_bucket{le="0.5"}[{{.window}}]))'
      total_query: 'sum(rate(http_request_duration_seconds_count[{{.window}}]))'
"""
        path = write_tmp_yaml(multi_yaml)
        service = load_service_slo(path)
        assert len(service.slos) == 2

    def test_service_id_normalised(self):
        path = write_tmp_yaml(VALID_SLO_YAML)
        service = load_service_slo(path)
        assert service.service_id == "test_service"
        assert "-" not in service.service_id

    def test_slo_error_rate_computed(self):
        path = write_tmp_yaml(VALID_SLO_YAML)
        service = load_service_slo(path)
        slo = service.slos[0]
        assert slo.error_rate == pytest.approx(0.001, rel=1e-5)
