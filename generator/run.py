"""
Main generator entrypoint.
Loads all SLO definitions and generates Prometheus rules + Grafana dashboards.

Usage:
    python -m generator.run
    python -m generator.run --service backend-api
    python -m generator.run --validate-only
"""
import argparse
import logging
import sys
from pathlib import Path

from .dashboard_generator import write_dashboard
from .loader import load_all_slos, load_service_slo
from .prometheus_generator import write_rules

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="SLO rule and dashboard generator")
    parser.add_argument("--service",       help="Generate for a specific service only")
    parser.add_argument("--validate-only", action="store_true", help="Validate YAML only, no output")
    parser.add_argument("--output-dir",    help="Override output directory")
    args = parser.parse_args()

    errors = []
    generated_rules      = []
    generated_dashboards = []

    if args.service:
        slo_path = Path(__file__).parent.parent / "slos" / "services" / f"{args.service}.yaml"
        if not slo_path.exists():
            logger.error("SLO file not found: %s", slo_path)
            sys.exit(1)
        services = [load_service_slo(slo_path)]
    else:
        services = list(load_all_slos())

    logger.info("Processing %d service SLO definition(s)...", len(services))

    for service_slo in services:
        try:
            if not args.validate_only:
                rules_path = write_rules(service_slo)
                generated_rules.append(rules_path)

                dash_path = write_dashboard(service_slo)
                generated_dashboards.append(dash_path)

            logger.info("✅ %s: %d SLOs", service_slo.service, len(service_slo.slos))

        except Exception as e:
            logger.error("❌ %s: %s", service_slo.service, e)
            errors.append((service_slo.service, str(e)))

    print()
    print("=" * 60)
    print(f"Generated {len(generated_rules)} Prometheus rule files")
    print(f"Generated {len(generated_dashboards)} Grafana dashboards")
    if errors:
        print(f"ERRORS: {len(errors)}")
        for svc, err in errors:
            print(f"  {svc}: {err}")
        sys.exit(1)
    print("=" * 60)


if __name__ == "__main__":
    main()
