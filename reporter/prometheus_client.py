"""
Prometheus query client for the SLO reporter.
Fetches current SLI and error budget data from Prometheus.
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import requests

logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus-operated.monitoring:9090")


class PrometheusClient:
    def __init__(self, url: str = PROMETHEUS_URL, timeout: int = 30):
        self.url     = url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"

    def query(self, promql: str) -> Optional[float]:
        """Execute an instant query and return the first scalar result."""
        try:
            resp = self.session.get(
                f"{self.url}/api/v1/query",
                params={"query": promql, "time": datetime.utcnow().isoformat()},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            if data["status"] != "success":
                logger.warning("Prometheus query failed: %s — %s", promql, data.get("error"))
                return None

            results = data["data"]["result"]
            if not results:
                return None

            return float(results[0]["value"][1])

        except requests.RequestException as e:
            logger.error("Prometheus request failed: %s", e)
            return None
        except (KeyError, IndexError, ValueError) as e:
            logger.error("Failed to parse Prometheus response: %s", e)
            return None

    def query_range(self, promql: str, start: datetime, end: datetime,
                    step: str = "1h") -> list[tuple[datetime, float]]:
        """Execute a range query and return (timestamp, value) pairs."""
        try:
            resp = self.session.get(
                f"{self.url}/api/v1/query_range",
                params={
                    "query": promql,
                    "start": start.isoformat(),
                    "end":   end.isoformat(),
                    "step":  step,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            if data["status"] != "success":
                return []

            results = []
            for ts, val in data["data"]["result"][0].get("values", []):
                results.append((datetime.fromtimestamp(ts), float(val)))
            return results

        except Exception as e:
            logger.error("Prometheus range query failed: %s", e)
            return []

    def get_sli(self, service_id: str, slo_id: str, window: str = "30d") -> Optional[float]:
        return self.query(f"slo:sli_{service_id}_{slo_id}:ratio_rate{window}")

    def get_error_budget_remaining(self, service_id: str, slo_id: str) -> Optional[float]:
        return self.query(f"slo:error_budget_remaining_{service_id}_{slo_id}")

    def get_error_budget_consumed(self, service_id: str, slo_id: str) -> Optional[float]:
        return self.query(f"slo:error_budget_consumed_{service_id}_{slo_id}")
