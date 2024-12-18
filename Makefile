# make > v4.0 required
SHELL := /bin/bash
.ONESHELL:

.PHONY: help
# From https://rosszurowski.com/log/2022/makefiles
help: ## Show this message
	@printf "\nSpecify a command. The choices are:\n\n"
	@grep -E '^[/0-9a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "; cyan = "\033[0;36m"; reset = "\033[0m";};
	{printf "  %s%-18s%s %s\n", cyan, $$1, reset, $$2}'
	echo ""

.PHONY: tidy
tidy: ## Format, clean, and check python codebase
	uv run ruff format
	uv run ruff check --fix
	uv run pyright

.PHONY: requirements
requirements: ## Sync and lock requirements
	uv sync
	uv lock

.PHONY: run
run: ## Run MCP server
	uv run mcp-python-helper
