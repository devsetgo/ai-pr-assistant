# Common developer commands for ai-pr-assistant.

# Core settings
PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
PYTEST ?= $(PYTHON) -m pytest

# Optional overrides:
# make test-file TEST_FILE=tests/test_llm.py
# make test-one TEST_NODE=tests/test_llm.py::test_generate_pr_content_classic_path
TEST_FILE ?= tests/test_llm.py
TEST_NODE ?= tests/test_llm.py::test_generate_pr_content_classic_path

# Build settings
IMAGE_NAME ?= ai-pr-assistant

# Version management helper (local binary fallback in some devcontainers)
BUMPCALVER = $(if $(wildcard $(HOME)/.local/bin/bumpcalver),$(HOME)/.local/bin/bumpcalver,bumpcalver)

.PHONY: help install test test-file test-one typecheck docker-build bump-preview docs-build docs-serve clean

help: ## Display this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_.-]+:.*?##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Install development dependencies
	$(PIP) install -r requirements-dev.txt

test: ## Run the full pytest suite with coverage
	$(PYTEST) -q

tests: test ## Alias for 'test' - Run the project's tests

test-file: ## Run one test file (override with TEST_FILE=...)
	$(PYTEST) $(TEST_FILE) -q

test-one: ## Run one pytest node (override with TEST_NODE=...)
	$(PYTEST) $(TEST_NODE) -q

typecheck: ## Run mypy for the action package
	mypy pr_description --python-version 3.12 --ignore-missing-imports

docker-build: ## Build the GitHub Action Docker image
	docker build -t $(IMAGE_NAME) .

docs-build: ## Build documentation site locally with Zensical
	zensical build --clean --strict

docs-serve: ## Serve docs locally with live reload
	zensical serve

bump-preview: ## Preview the next CalVer bump without writing/tagging
	$(BUMPCALVER) --build --dry-run --json

clean: ## Remove common generated artifacts
	rm -rf htmlcov .pytest_cache .mypy_cache
