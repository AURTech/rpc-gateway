.DEFAULT_GOAL := help

.PHONY: help test test-api test-web

TESTS ?=
PYTEST_ARGS ?=
VITEST_ARGS ?=

help:
	@printf "RPC Gateway repo targets:\n"
	@printf "  make test TESTS=server/tests/jsonrpc_forwarding/test_manager.py  Run targeted API tests\n"
	@printf "  make test TESTS=web/src/api/auth/actions.test.ts    Run targeted web tests\n"
	@printf "  make test-api TESTS=tests/jsonrpc_forwarding/test_manager.py     Run API tests from server/\n"
	@printf "  make test-web TESTS=src/api/auth/actions.test.ts    Run web tests from web/\n"
	@printf "\n"
	@printf "Optional args:\n"
	@printf "  PYTEST_ARGS='-k quota'       Extra pytest args for API tests\n"
	@printf "  VITEST_ARGS='--reporter dot' Extra Vitest args for web tests\n"
	@printf "\n"
	@printf "Unscoped make test intentionally does not run the full suite.\n"

test:
	@if [ -z "$(TESTS)" ]; then \
		printf "TESTS is required. Use a targeted path, for example:\n"; \
		printf "  make test TESTS=server/tests/jsonrpc_forwarding/test_manager.py\n"; \
		printf "  make test TESTS=web/src/api/auth/actions.test.ts\n"; \
		exit 2; \
	fi
	@case "$(TESTS)" in \
		server/*) target="$(TESTS)"; target="$${target#server/}"; $(MAKE) -C server test TESTS="$$target" PYTEST_ARGS="$(PYTEST_ARGS)" ;; \
		web/*) target="$(TESTS)"; target="$${target#web/}"; $(MAKE) -C web test TESTS="$$target" VITEST_ARGS="$(VITEST_ARGS)" ;; \
		*) printf "TESTS must start with server/ or web/ when using root make test.\n"; exit 2 ;; \
	esac

test-api:
	@if [ -z "$(TESTS)" ]; then \
		printf "TESTS is required. Example: make test-api TESTS=tests/jsonrpc_forwarding/test_manager.py\n"; \
		exit 2; \
	fi
	@$(MAKE) -C server test TESTS="$(TESTS)" PYTEST_ARGS="$(PYTEST_ARGS)"

test-web:
	@if [ -z "$(TESTS)" ]; then \
		printf "TESTS is required. Example: make test-web TESTS=src/api/auth/actions.test.ts\n"; \
		exit 2; \
	fi
	@$(MAKE) -C web test TESTS="$(TESTS)" VITEST_ARGS="$(VITEST_ARGS)"
