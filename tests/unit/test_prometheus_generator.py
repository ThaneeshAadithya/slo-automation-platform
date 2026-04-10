"""Unit tests for the Prometheus rule generator."""
import pytest

from generator.models import AlertingConfig, Annotations, MetricConfig, SLODefinition, ServiceSLO
from generator.prometheus_generator import (
    _sli_ratio_expr,
    generate_service_rules,
    BURN_RATE_WINDOWS,
)


def make_service_slo(
    service="backend-api",
    slo_name="availability",
    slo_type="availability",
    target=0.999,
    window="30d",
) -> ServiceSLO:
    return ServiceSLO(
        service=service,
        team="platform",
        namespace="backend",
        slos=[
            SLODefinition(
                name=slo_name,
                slo_type=slo_type,
                target=target,
                window=window,
                description="Test SLO",
                metric=MetricConfig(
                    good_query='sum(rate(http_requests_total{status!~"5.."}[{{.window}}]))',
                    total_query="sum(rate(http_requests_total[{{.window}}]))",
                ),
                alerting=AlertingConfig(
                    page_on_burn=True,
                    ticket_on_budget_low=True,
                    budget_low_threshold=0.10,
                ),
                annotations=Annotations(
                    runbook_url="https://runbooks.example.com/test",
                ),
            )
        ],
    )


class TestSLIRatioExpr:
    def test_substitutes_window_in_good_query(self):
        slo = make_service_slo().slos[0]
        expr = _sli_ratio_expr(slo, "5m")
        assert "5m" in expr
        assert "{{.window}}" not in expr

    def test_substitutes_window_in_total_query(self):
        slo = make_service_slo().slos[0]
        expr = _sli_ratio_expr(slo, "1h")
        assert "1h" in expr

    def test_contains_division(self):
        slo = make_service_slo().slos[0]
        expr = _sli_ratio_expr(slo, "30d")
        assert "/" in expr

    def test_handles_different_windows(self):
        slo = make_service_slo().slos[0]
        for window in ["5m", "30m", "1h", "2h", "6h", "1d", "3d", "30d"]:
            expr = _sli_ratio_expr(slo, window)
            assert window in expr
            assert "{{.window}}" not in expr


class TestGenerateServiceRules:
    def test_returns_dict_with_required_keys(self):
        service_slo = make_service_slo()
        rules = generate_service_rules(service_slo)
        assert rules["apiVersion"] == "monitoring.coreos.com/v1"
        assert rules["kind"] == "PrometheusRule"
        assert "metadata" in rules
        assert "spec" in rules

    def test_metadata_includes_service_name(self):
        service_slo = make_service_slo(service="backend-api")
        rules = generate_service_rules(service_slo)
        assert "backend-api" in rules["metadata"]["name"]

    def test_generates_recording_and_alert_groups(self):
        service_slo = make_service_slo()
        rules = generate_service_rules(service_slo)
        groups = rules["spec"]["groups"]
        group_names = [g["name"] for g in groups]
        # Should have at least one recording group and one alert group
        assert any("recording" in n for n in group_names)
        assert any("alert" in n for n in group_names)

    def test_recording_rules_cover_all_windows(self):
        service_slo = make_service_slo()
        rules = generate_service_rules(service_slo)
        groups = rules["spec"]["groups"]

        recording_groups = [g for g in groups if "recording" in g["name"]]
        assert recording_groups, "Must have recording rules group"

        rule_names = [r["record"] for r in recording_groups[0]["rules"]]
        for window in ["5m", "30m", "1h", "2h", "6h", "1d", "3d", "30d"]:
            assert any(window in name for name in rule_names), \
                f"Missing recording rule for window {window}"

    def test_error_budget_recording_rules_present(self):
        service_slo = make_service_slo()
        rules = generate_service_rules(service_slo)
        all_rules = [r for g in rules["spec"]["groups"] for r in g.get("rules", [])]
        rule_names = [r.get("record", "") for r in all_rules]
        assert any("error_budget_remaining" in n for n in rule_names)
        assert any("error_budget_consumed" in n for n in rule_names)

    def test_burn_rate_alerts_generated(self):
        service_slo = make_service_slo()
        rules = generate_service_rules(service_slo)
        all_rules = [r for g in rules["spec"]["groups"] for r in g.get("rules", [])]
        alert_names = [r.get("alert", "") for r in all_rules if "alert" in r]
        # Should have burn rate alerts for at least the page-worthy windows
        assert len(alert_names) >= 2, "Must generate at least 2 burn rate alerts"

    def test_alert_has_required_labels(self):
        service_slo = make_service_slo(service="backend-api")
        rules = generate_service_rules(service_slo)
        all_rules = [r for g in rules["spec"]["groups"] for r in g.get("rules", [])]
        alerts = [r for r in all_rules if "alert" in r]
        for alert in alerts:
            assert "labels" in alert
            assert "severity" in alert["labels"]
            assert "service"  in alert["labels"]
            assert "team"     in alert["labels"]

    def test_alert_has_runbook_url(self):
        service_slo = make_service_slo()
        rules = generate_service_rules(service_slo)
        all_rules = [r for g in rules["spec"]["groups"] for r in g.get("rules", [])]
        alerts = [r for r in all_rules if "alert" in r]
        for alert in alerts:
            assert "annotations" in alert
            assert "runbook_url" in alert["annotations"]

    def test_budget_low_alert_generated(self):
        service_slo = make_service_slo()
        rules = generate_service_rules(service_slo)
        all_rules = [r for g in rules["spec"]["groups"] for r in g.get("rules", [])]
        alert_names = [r.get("alert", "") for r in all_rules]
        assert any("BudgetLow" in n or "budget" in n.lower() for n in alert_names), \
            "Must generate an error budget low alert"

    def test_no_page_alerts_when_disabled(self):
        service_slo = make_service_slo()
        service_slo.slos[0].alerting.page_on_burn = False
        rules = generate_service_rules(service_slo)
        all_rules = [r for g in rules["spec"]["groups"] for r in g.get("rules", [])]
        alerts = [r for r in all_rules if "alert" in r]
        page_alerts = [a for a in alerts if a.get("labels", {}).get("alert_type") == "page"]
        assert len(page_alerts) == 0, "No page alerts should be generated when page_on_burn=False"

    def test_skips_slo_without_metric(self):
        service_slo = make_service_slo()
        service_slo.slos[0].metric = None  # Remove metric
        rules = generate_service_rules(service_slo)
        # Should still return valid structure, just with empty groups
        assert rules["apiVersion"] == "monitoring.coreos.com/v1"

    def test_high_target_low_error_budget(self):
        # 99.99% target → very low burn rate thresholds
        service_slo = make_service_slo(target=0.9999)
        slo = service_slo.slos[0]
        assert slo.error_rate == pytest.approx(0.0001, rel=1e-5)

    def test_slo_target_pct_format(self):
        slo = make_service_slo(target=0.999).slos[0]
        assert slo.target_pct == "99.900%"

    def test_payment_service_stricter_target(self):
        service_slo = make_service_slo(service="payment-service", target=0.9995)
        rules = generate_service_rules(service_slo)
        assert rules["metadata"]["name"] == "slo-payment-service"


class TestBurnRateWindows:
    def test_burn_rate_windows_are_ordered_by_burn_rate_desc(self):
        rates = [bw[2] for bw in BURN_RATE_WINDOWS]
        assert rates == sorted(rates, reverse=True), \
            "Burn rate windows should be ordered highest rate first"

    def test_fast_burn_windows_are_critical(self):
        for short, long, rate, severity, action in BURN_RATE_WINDOWS:
            if rate >= 6:
                assert severity == "critical", f"Rate {rate}x should be critical"

    def test_at_least_one_page_and_one_ticket(self):
        actions = [bw[4] for bw in BURN_RATE_WINDOWS]
        assert "page"   in actions
        assert "ticket" in actions
