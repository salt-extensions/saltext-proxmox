GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
CYAN   := $(shell tput -Txterm setaf 6)
BOLD   := $(shell tput -Txterm bold)
ULINE  := $(shell tput -Txterm smul)
RESET  := $(shell tput -Txterm sgr0)

.DEFAULT_GOAL:=help

VENV_SH = sh -c '. .venv/bin/activate && exec "$$@"' _


.PHONY: help
help:
	@echo ''
	@echo '${ULINE}Usage:${RESET}'
	@echo '    ${YELLOW}make${RESET} ${GREEN}<TARGET>${RESET}'
	@echo ''
	@echo ''
	@echo '${ULINE}Targets:${RESET}'
	@awk 'BEGIN {FS = ":.*?## "} { \
		if (/^[a-zA-Z_-]+:.*?##.*$$/) {printf "     ${BOLD}${GREEN}%-20s${RESET}%s\n", $$1, $$2} \
		else if (/^## .*$$/) {printf "\n  ${CYAN}[%s]${RESET}\n", substr($$1,4)} \
		}' $(MAKEFILE_LIST)

## Lifecycle

.PHONY: dev
dev: ## Create dev venv, force project (re-)install into it
	@python tools/initialize.py

# Internal: ensure the dev venv exists and is in sync with pyproject.toml,
# skipping the project install otherwise (unlike `dev`, which forces it).
.PHONY: dev-sync
dev-sync:
	@python tools/initialize.py --skip-install

.PHONY: clean
clean: ## Remove: project/nox venvs, built docs
	@rm -rf .nox .venv docs/_build

## Code

# The hooks are tagged with prek groups matching these target names.
# The pre-commit fallback does not support groups, run the member
# hooks individually instead (listed via tools/hook_group.py).
.PHONY: fmt lint
fmt: ## Run all formatting hooks on all files
lint: ## Run all lint/check hooks on all files
fmt lint: dev-sync
	@$(VENV_SH) sh -c 'if command -v prek >/dev/null 2>&1; then \
			exec prek run --all-files --group $@; \
		fi; \
		rc=0; \
		for hook in $$(python tools/hook_group.py $@); do \
			python tools/pre_commit_quiet.py run --all-files "$$hook" || rc=1; \
		done; \
		exit "$$rc"'

## Docs

.PHONY: changelog
changelog: dev-sync ## Render changelog. Requires VERSION parameter.
	@if [ -z "$(VERSION)" ]; then \
		echo "Missing VERSION parameter. Example: make changelog VERSION=1.0.0" >&2; exit 1; \
	fi
	@$(VENV_SH) towncrier build --yes --version='$(VERSION)'

.PHONY: docs
docs: dev-sync ## Build docs
	@$(VENV_SH) nox -e docs

.PHONY: docs-dev
docs-dev: dev-sync ## Build docs, serve them and refresh on changes
	@$(VENV_SH) nox -e docs-dev

## Tests

.PHONY: tests
tests: dev-sync ## Run tests
	@$(VENV_SH) nox -e test

.PHONY: cov-dev
cov-dev: dev-sync ## Build HTML coverage report, serve it and refresh on new test runs
	@$(VENV_SH) nox -e cov-dev
