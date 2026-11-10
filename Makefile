COMPOSE = docker compose
MANAGE  = $(COMPOSE) exec api python manage.py

.PHONY: help setup up down logs migrate test-setup demo-data reset schema test shell psql clean

help: ## Show all commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-12s %s\n", $$1, $$2}'

setup: up migrate test-setup ## First run: start, migrate and seed

up: ## Start Postgres + API in the background
	$(COMPOSE) up -d --build

down: ## Stop everything (data is kept)
	$(COMPOSE) down

logs: ## Follow API logs
	$(COMPOSE) logs -f api

migrate: ## Create + apply database migrations
	$(MANAGE) makemigrations compliance
	$(MANAGE) migrate

test-setup: ## Load reference data + baseline test users
	$(MANAGE) seed

demo-data: ## Add sample suppliers, certificates and audits to click around
	$(MANAGE) seed --sample-data

reset: ## Wipe all data and reload the baseline
	$(MANAGE) reset_db

schema: ## Export the OpenAPI schema to openapi.yaml (for Postman / codegen)
	$(MANAGE) spectacular --file openapi.yaml
	@echo "Written to openapi.yaml"

test: ## Run the backend's own Django tests
	$(MANAGE) test compliance

shell: ## Django shell
	$(MANAGE) shell

psql: ## Open psql on the database
	$(COMPOSE) exec db psql -U compliance -d compliance

clean: ## Stop and DELETE the database volume
	$(COMPOSE) down -v
