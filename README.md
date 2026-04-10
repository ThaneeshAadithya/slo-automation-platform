# 📊 slo-automation-platform

> SLO lifecycle automation — define SLOs in YAML, auto-generate Prometheus recording rules,
> burn rate alerts, Grafana dashboards, weekly error budget reports, and PagerDuty incidents.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)
![Prometheus](https://img.shields.io/badge/Prometheus-Rules-E6522C?logo=prometheus)
![Grafana](https://img.shields.io/badge/Grafana-Dashboards-F46800?logo=grafana)
![PagerDuty](https://img.shields.io/badge/PagerDuty-Incidents-25C151)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 🏗️ Architecture

```
slos/services/*.yaml  ← source of truth (Git)
         │
         ▼
   generator/        ← Python: reads YAML, generates everything
         │
    ┌────┴──────────────────────────────────────────┐
    │               │              │                 │
    ▼               ▼              ▼                 ▼
prometheus/    dashboards/    alerting/          reporter/
generated/     grafana/       pagerduty/         weekly HTML report
 *.yaml         *.json         incidents          + Slack digest
(rules +       (canary vs     (auto-create        + email
 recording)     stable)        on breach)
```

---

## ✨ What's Included

| Component | Description |
|-----------|-------------|
| **SLO Definitions** | YAML schema — availability, latency, error-rate SLOs per service |
| **Rule Generator** | Python generates Prometheus recording rules + multi-window burn rate alerts |
| **Dashboard Generator** | Python generates Grafana JSON dashboards per SLO (error budget, burn rate) |
| **Weekly Reporter** | HTML + text reports — error budget consumed, trend, at-risk services |
| **PagerDuty Integration** | Auto-create incidents when SLO is breached; resolve when recovered |
| **Slack Digest** | Weekly #slo-status digest — budget remaining per service |
| **Email Report** | HTML email with full SLO state for engineering leadership |
| **CI Pipeline** | Validate YAML → Generate rules/dashboards → Diff check → Apply |

---

## 📁 Repository Structure

```
slo-automation-platform/
├── slos/
│   ├── schemas/          # JSON Schema for SLO YAML validation
│   └── services/         # One YAML per service
│       ├── backend-api.yaml
│       ├── payment-service.yaml
│       └── auth-service.yaml
├── generator/            # Python SLO → Prometheus/Grafana generator
├── reporter/             # Weekly report generator
│   ├── templates/        # Jinja2 HTML email templates
│   └── email/            # Email sender
├── alerting/
│   ├── pagerduty/        # PD incident create/resolve
│   └── slack/            # Slack digest
├── dashboards/
│   ├── grafana/          # Generated dashboard JSON (committed)
│   └── templates/        # Jinja2 dashboard templates
├── prometheus/
│   └── generated/        # Generated Prometheus rules (committed)
├── tests/                # pytest unit + integration tests
├── scripts/              # CLI helpers
└── docs/                 # SLO guide + burn rate explainer
```

---

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Validate all SLO definitions
python -m generator.validate

# Generate Prometheus rules + Grafana dashboards
python -m generator.run

# Preview weekly report
python -m reporter.generate --dry-run

# Apply generated rules to cluster
kubectl apply -f prometheus/generated/
```

## 📄 License  MIT
