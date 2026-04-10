"""
SLO definition validator.
Validates all YAML files against schema without generating output.

Usage:
    python -m generator.validate
"""
import logging
import sys

from .loader import load_all_slos

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)


def main():
    errors = []
    total_slos = 0

    for service_slo in load_all_slos():
        total_slos += len(service_slo.slos)
        for slo in service_slo.slos:
            if slo.metric is None:
                errors.append(f"{service_slo.service}/{slo.name}: missing metric config")
            elif not slo.metric.good_query.strip():
                errors.append(f"{service_slo.service}/{slo.name}: empty good_query")
            elif not slo.metric.total_query.strip():
                errors.append(f"{service_slo.service}/{slo.name}: empty total_query")

            if not 0 < slo.target < 1:
                errors.append(f"{service_slo.service}/{slo.name}: target must be between 0 and 1 (got {slo.target})")

        logger.info("✅ %s: %d SLOs validated", service_slo.service, len(service_slo.slos))

    print()
    print(f"Validated {total_slos} SLO definitions")
    if errors:
        print("VALIDATION ERRORS:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("All SLO definitions valid ✅")


if __name__ == "__main__":
    main()
