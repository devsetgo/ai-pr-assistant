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

# Which bumpcalver flavour `make bump` applies: build | beta | rc
BUMP ?= build

# bumpcalver's changelog step needs OPENAI_API_KEY (see [tool.bumpcalver.changelog]);
# load it from the git-ignored .env when there is one.
LOAD_ENV = if [ -f .env ]; then set -a; . ./.env; set +a; fi

# Version management helper (local binary fallback in some devcontainers)
BUMPCALVER = $(if $(wildcard $(HOME)/.local/bin/bumpcalver),$(HOME)/.local/bin/bumpcalver,bumpcalver)

.PHONY: help install hooks lint format docs-index test test-file test-one typecheck lock docker-build bump-preview bump docs-build docs-serve clean git-cleanup

help: ## Display this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_.-]+:.*?##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Install development dependencies
	$(PIP) install -r requirements-dev.txt

hooks: ## Install the git pre-commit hook (ruff)
	pre-commit install

lint: ## Run ruff lint checks (no changes written)
	ruff check .

format: ## Apply ruff lint fixes and formatting
	ruff check --fix .
	ruff format .

test: ## Run the project's tests (format + pre-commit + mypy + pytest + coverage badges)
	@set -e; start=$$(date +%s); \
	echo "🎨 Applying ruff fixes and formatting..."; \
	$(MAKE) --no-print-directory format docs-index; \
	echo "🔍 Running pre-commit (ruff lint + format)..."; \
	$(PYTHON) -m pre_commit run -a; \
	echo "✅ Pre-commit passed. Running type check..."; \
	$(MAKE) --no-print-directory typecheck; \
	echo "✅ Type check passed. Running full pytest suite..."; \
	$(PYTEST) -q --cov-report=xml --junitxml=report.xml; \
	echo "📊 Generating coverage and test badges..."; \
	mkdir -p docs/badges; \
	genbadge coverage -i coverage.xml -o docs/badges/coverage-badge.svg; \
	genbadge tests -i report.xml -o docs/badges/tests-badge.svg; \
	end=$$(date +%s); \
	echo "✨ Tests complete. Badges updated. Total time: $$((end - start)) seconds"

tests: test ## Alias for 'test' - Run the project's tests

test-file: ## Run one test file (override with TEST_FILE=...)
	$(PYTEST) $(TEST_FILE) -q

test-one: ## Run one pytest node (override with TEST_NODE=...)
	$(PYTEST) $(TEST_NODE) -q

typecheck: ## Run mypy for the action package
	mypy pr_description --python-version 3.12 --ignore-missing-imports

lock: ## Regenerate requirements.lock (hashed, wheels-only) that the Docker image installs from
	pip-compile --generate-hashes --strip-extras --pip-args "--only-binary=:all:" --output-file requirements.lock requirements.txt

docker-build: ## Build the GitHub Action Docker image
	docker build -t $(IMAGE_NAME) .

docs-index: ## Regenerate docs/index.md from README.md
	$(PYTHON) scripts/sync_docs_index.py

docs-build: docs-index ## Build documentation site locally with Zensical
	zensical build --clean --strict

docs-serve: docs-index ## Serve docs locally with live reload
	zensical serve

bump-preview: ## Preview the next CalVer bump without writing/tagging
	@$(LOAD_ENV); $(BUMPCALVER) --build --dry-run --json

bump: ## Bump the CalVer version + changelog, commit and tag locally (BUMP=build|beta|rc)
	@set -e; \
	case "$(BUMP)" in build|beta|rc) ;; *) echo "BUMP must be build, beta or rc (got '$(BUMP)')"; exit 1 ;; esac; \
	if [ -n "$$(git status --porcelain)" ]; then \
		echo "Working tree is not clean - commit or stash first so the bump commit holds only the version change."; \
		exit 1; \
	fi; \
	$(LOAD_ENV); \
	echo "Bumping version ($(BUMP))..."; \
	$(BUMPCALVER) --$(BUMP) --update-changelog; \
	echo "Bumped and tagged $$(git describe --tags --abbrev=0) locally (nothing pushed). Review: git show --stat HEAD"; \
	echo "Publish with: git push origin HEAD $$(git describe --tags --abbrev=0)"

clean: ## Remove common generated artifacts
	rm -rf htmlcov .pytest_cache .mypy_cache coverage.xml report.xml

# `git branch -D` (force) is deliberate: a squash-merged branch's commits never appear in
# main's history, so `-d` would refuse to delete every branch merged that way. The cost is
# that a branch with unpushed local commits is lost if its remote branch was deleted (only
# recoverable via `git reflog`). main/master/dev and the checked-out branch are never touched.
git-cleanup: ## Fetch + prune from origin, then delete local branches whose upstream is gone
	@echo "Fetching from origin and pruning stale remote-tracking branches..."
	git fetch origin --prune
	@echo "Removing local branches whose upstream branch no longer exists..."
	@git for-each-ref --format='%(refname:short) %(upstream:track)' refs/heads \
		| awk '$$2 == "[gone]" {print $$1}' \
		| grep -vxE 'main|master|dev' \
		| grep -vxF "$$(git branch --show-current)" \
		| xargs -r git branch -D
	@echo "git-cleanup complete."
