"""Unit tests for SLO data models."""
import pytest
from generator.models import SLODefinition, ServiceSLO, MetricConfig, AlertingConfig


def make_slo(target: float = 0.999) -> SLODefinition:
    return SLODefinition(
        name="availability",
        slo_type="availability",
        target=target,
        window="30d",
        metric=MetricConfig(good_query="good", total_query="total"),
    )


class TestSLODefinition:
    def test_error_rate_complements_target(self):
        slo = make_slo(0.999)
        assert slo.error_rate == pytest.approx(0.001)

    def test_error_rate_for_four_nines(self):
        slo = make_slo(0.9999)
        assert slo.error_rate == pytest.approx(0.0001)

    def test_target_pct_formatting(self):
        assert make_slo(0.999).target_pct   == "99.900%"
        assert make_slo(0.9999).target_pct  == "99.990%"
        assert make_slo(0.9995).target_pct  == "99.950%"

    def test_slo_id_replaces_hyphens(self):
        slo = SLODefinition("my-slo-name", "availability", 0.99, "30d")
        assert "-" not in slo.slo_id
        assert slo.slo_id == "my_slo_name"

    def test_slo_id_is_lowercase(self):
        slo = SLODefinition("MyAvailability", "availability", 0.99, "30d")
        assert slo.slo_id == slo.slo_id.lower()


class TestServiceSLO:
    def test_service_id_normalisation(self):
        svc = ServiceSLO("backend-api", "platform", "backend", [])
        assert svc.service_id == "backend_api"

    def test_service_id_no_hyphens(self):
        svc = ServiceSLO("payment-service", "payments", "payments", [])
        assert "-" not in svc.service_id
