# SLO Definition Guide

## Adding a New Service SLO

1. Create `slos/services/my-service.yaml`
2. Follow the schema in `slos/schemas/slo-schema.json`
3. Open a PR — CI validates YAML + generates rules + shows diff
4. Merge — rules are auto-applied to the cluster

## SLO Types

| Type | When to use | Metric |
|------|-------------|--------|
| `availability` | API success rate | `requests_total{status!~"5.."} / requests_total` |
| `latency` | Response time | `request_duration_bucket{le=threshold} / request_duration_count` |
| `error_rate` | Business errors | `errors_total / transactions_total` |

## Target Setting Recommendations

| Service Type | Recommended Target |
|-------------|-------------------|
| Internal tools | 99.5% (87.6h/year budget) |
| Customer-facing APIs | 99.9% (8.7h/year budget) |
| Payment / auth services | 99.95% (4.4h/year budget) |
| Core infrastructure | 99.99% (52m/year budget) |

## Multi-Window Burn Rate Alerts

This platform uses the Google SRE Workbook approach:

| Window Pair | Burn Rate | Severity | Action |
|-------------|-----------|----------|--------|
| 5m + 1h     | 14.4×     | Critical | Page   |
| 30m + 6h    | 6×        | Critical | Page   |
| 2h + 1d     | 3×        | Warning  | Ticket |
| 6h + 3d     | 1×        | Warning  | Ticket |

**Why two windows?** Using two windows prevents false alarms from brief spikes.
Both the short and long window must breach the threshold before alerting.

## Error Budget Mathematics

```
Error budget (monthly) = (1 - target) × 30 × 24 × 60 minutes

Example (99.9% SLO):
  = (1 - 0.999) × 43,200
  = 0.001 × 43,200
  = 43.2 minutes allowed downtime per month

Fast burn at 14.4×:
  = consuming 14.4 × 0.001 = 1.44% of requests failing
  = exhausts budget in: 43.2 / 14.4 = 3 hours
```
