# UK Bill Pipeline
#
# Every target here works on Linux, macOS and in GitHub Actions. On Windows,
# run them from Git Bash, or use the PowerShell equivalents in
# docs/deployment.md.
#
# Nothing in this file needs AWS credentials. The targets that would touch AWS
# live in .github/workflows/deploy.yml and in scripts/, and are run
# deliberately rather than as part of `make check`.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

PYTHON ?= python3
VENV := .venv
VENV_BIN := $(VENV)/bin
ifeq ($(OS),Windows_NT)
	VENV_BIN := $(VENV)/Scripts
endif
VENV_PYTHON := $(VENV_BIN)/python

TF ?= terraform
TF_DIRS := infra/bootstrap infra/environments/prod
TF_TEST_DIRS := infra/modules/static_delivery infra/modules/ingestion infra/environments/prod

.PHONY: help
help: ## Show the available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

.PHONY: install
install: ## Install frontend and Python development dependencies
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e "backend[dev]"
	cd frontend && npm ci

# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

.PHONY: lint
lint: ## Ruff, mypy, ESLint and TypeScript checks
	cd backend && ../$(VENV_PYTHON) -m ruff check .
	cd backend && ../$(VENV_PYTHON) -m ruff format --check .
	cd backend && ../$(VENV_PYTHON) -m mypy
	cd frontend && npm run lint
	cd frontend && npm run format:check
	cd frontend && npm run typecheck

.PHONY: test
test: ## Backend and frontend unit and contract tests
	cd backend && ../$(VENV_PYTHON) -m pytest --cov --cov-report=term-missing
	cd frontend && npm run test

.PHONY: test-e2e
test-e2e: ## Playwright tests against the production build
	cd frontend && npm run test:e2e

.PHONY: fixtures
fixtures: ## Regenerate the synthetic example snapshot
	$(VENV_PYTHON) scripts/build_synthetic_snapshot.py

.PHONY: fixtures-check
fixtures-check: ## Fail if the checked-in example snapshot is out of date
	$(VENV_PYTHON) scripts/build_synthetic_snapshot.py --check

.PHONY: docs
docs: ## Regenerate the stage mapping documentation from the mapping table
	$(VENV_PYTHON) scripts/generate_stage_mapping_docs.py

.PHONY: docs-check
docs-check: ## Fail if docs/stage-mapping.md no longer matches the mapping table
	$(VENV_PYTHON) scripts/generate_stage_mapping_docs.py --check

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

.PHONY: build
build: build-lambda build-frontend ## Build the Lambda package and the frontend

.PHONY: build-lambda
build-lambda: ## Build the ingestion Lambda package for Terraform to zip
	bash scripts/build_lambda.sh $(abspath $(VENV_PYTHON))

.PHONY: build-frontend
build-frontend: ## Type-check and build the production frontend
	cd frontend && npm run build

# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

.PHONY: tf-validate
tf-validate: ## Format check, validate and policy-check the Terraform
	$(TF) fmt -recursive -check -diff infra
	@for dir in $(TF_DIRS); do \
		echo "==> $$dir"; \
		$(TF) -chdir=$$dir init -backend=false -input=false >/dev/null; \
		$(TF) -chdir=$$dir validate; \
	done
	$(VENV_PYTHON) scripts/check_infra_policy.py

.PHONY: tf-test
tf-test: ## Terraform policy tests, using mocked providers and no credentials
	@for dir in $(TF_TEST_DIRS); do \
		echo "==> $$dir"; \
		$(TF) -chdir=$$dir init -backend=false -input=false >/dev/null; \
		$(TF) -chdir=$$dir test; \
	done

.PHONY: tf-fmt
tf-fmt: ## Format the Terraform sources in place
	$(TF) fmt -recursive infra

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

.PHONY: dev
dev: ## Run Vite against the synthetic snapshot
	cd frontend && npm run dev

.PHONY: repo-check
repo-check: ## Licence attribution and no state or credentials committed
	$(VENV_PYTHON) scripts/check_repository.py

# Deliberately the same set the CI workflow runs, minus the browser tests,
# which need a Playwright download. `make check && make test-e2e` is the whole
# gate. If these two lists ever drift, CI is no longer reproducible locally.
.PHONY: check
check: lint test fixtures-check docs-check repo-check tf-validate tf-test ## Every non-deployment quality check

.PHONY: clean
clean: ## Remove build output and caches
	rm -rf backend/build frontend/dist frontend/coverage
	rm -rf frontend/playwright-report frontend/test-results
	find . -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.terraform' -prune -exec rm -rf {} + 2>/dev/null || true
