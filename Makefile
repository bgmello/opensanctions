# SHELL specifies the shell used by Make. Bash is used for its array and string manipulation capabilities.
SHELL := /bin/bash

# Check if 'docker-compose' is available, if not, use 'docker compose'.
COMPOSE_CMD := $(if $(shell which docker-compose 2>/dev/null),docker-compose,docker compose)

.PHONY: build

all: run

workdir:
	mkdir -p data/

build:
	$(COMPOSE_CMD) build --pull

shell: build workdir
	$(COMPOSE_CMD) run --rm app bash

run: build workdir
	$(COMPOSE_CMD) run --rm app opensanctions run

stop:
	$(COMPOSE_CMD) down --remove-orphans

clean:
	rm -rf data/datasets build dist .mypy_cache .pytest_cache