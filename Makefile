.PHONY: help validate generate test report apply clean

help:
	@echo "Targets:"
	@echo "  validate        Validate all SLO YAML definitions"
	@echo "  generate        Generate Prometheus rules + Grafana dashboards"
	@echo "  test            Run all unit tests"
	@echo "  test-cov        Run tests with coverage report"
	@echo "  report          Generate weekly report (dry-run)"
	@echo "  report-send     Generate and send weekly report"
	@echo "  apply           Apply generated rules to current kubectl context"
	@echo "  lint            Run ruff + black linter"
	@echo "  install         Install dependencies"

install:
	pip install -r requirements.txt

validate:
	python -m generator.validate

generate:
	python -m generator.run

generate-service:
	python -m generator.run --service $(SERVICE)

test:
	pytest tests/ -v -x

test-cov:
	pytest tests/ -v --cov=generator --cov=reporter --cov=alerting \
		--cov-report=html --cov-report=term-missing

report:
	python -m reporter.generate --dry-run --output-html /tmp/slo-report.html
	@echo "Report: /tmp/slo-report.html"

report-send:
	python -m reporter.generate --output-html /tmp/slo-report.html

apply:
	kubectl apply -f prometheus/generated/ -n monitoring
	@echo "Applied. Check: kubectl get prometheusrule -n monitoring -l slo-managed=true"

lint:
	ruff check . && black --check .

fmt:
	black . && ruff check --fix .

clean:
	find . -type d -name __pycache__ | xargs rm -rf
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage
