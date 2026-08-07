.DEFAULT_GOAL := help

.PHONY: help init build check test verify push-origin push-aur

TESTS ?=
VITEST_ARGS ?=

help:
	@printf "RPC Gateway Make targets:\n"
	@printf "  make init        Enable corepack and install dependencies\n"
	@printf "  make build       Build the production app\n"
	@printf "  make check       Run CI baseline checks\n"
	@printf "  make test        Run unit and component tests (optionally TESTS=src/path.test.ts)\n"
	@printf "  make verify      Run delivery gate: check and build\n"
	@printf "  make push-origin Push local main to origin/main\n"
	@printf "  make push-aur    Push local aur to aur/main\n"

init:
	corepack enable
	pnpm install

build:
	pnpm build:worker

check:
	pnpm check

test:
	@if [ -n "$(TESTS)$(VITEST_ARGS)" ]; then \
		pnpm test -- $(TESTS) $(VITEST_ARGS); \
	else \
		pnpm test; \
	fi

verify:
	pnpm verify

push-origin:
	git push origin main

push-aur:
	git push aur aur:main
