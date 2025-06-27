GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
BOLD   := $(shell tput -Txterm bold)
ULINE  := $(shell tput -Txterm smul)
RESET  := $(shell tput -Txterm sgr0)

.DEFAULT_GOAL:=help


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
dev: ## Create dev venv, (re-)install project in it
	@python tools/initialize.py

.PHONY: clean
clean: ## Remove: project/nox venvs, built docs
	@rm -rf .nox .venv docs/_build

## Docs

.PHONY: docs
changelog: dev ## Render changelog. Requires VERSION parameter.
	@if [ -z "$(VERSION)" ]; then \
		echo "Missing VERSION parameter. Example: make changelog VERSION=1.0.0" >&2; exit 1; \
	fi; \
    source .venv/bin/activate; \
	towncrier build --yes --version='$(VERSION)'

.PHONY: docs
docs: dev ## Build docs
	@source .venv/bin/activate; \
	  nox -e docs --extra-pythons=3.10 --python=3.10

.PHONY: docs-dev
docs-dev: dev ## Build docs, serve them and refresh on changes
	@source .venv/bin/activate; \
	  nox -e docs-dev --extra-pythons=3.10 --python=3.10

## Tests

.PHONY: tests
tests: dev ## Run tests
	@source .venv/bin/activate; \
	  nox -e tests-3.10
