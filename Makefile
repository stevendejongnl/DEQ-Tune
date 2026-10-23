.PHONY: help install install-backend install-frontend \
        dev dev-backend dev-frontend dev-simulator dev-sim console warm \
        test test-backend test-frontend e2e e2e-install \
        typecheck generate-dto check-real-deq clean

BACKEND_PORT := 8420
FRONTEND_PORT := 5173

help:
	@echo "Targets:"
	@echo "  make install        Install backend and frontend dependencies"
	@echo "  make dev            Run backend and frontend dev servers together"
	@echo "  make dev-backend    Run only the backend dev server (port $(BACKEND_PORT))"
	@echo "  make dev-frontend   Run only the frontend dev server (port $(FRONTEND_PORT))"
	@echo "  make dev-sim        Run the whole stack against a simulated DEQ you can change"
	@echo "  make dev-simulator  Run only the backend against that simulated DEQ"
	@echo "  make console        Change what the simulated DEQ reports (run beside it)"
	@echo "  make warm           Pre-build the frontend dependency cache (once, ~1s)"
	@echo "  make test           Run backend and frontend tests"
	@echo "  make e2e            Run the end-to-end tests in a real browser"
	@echo "  make e2e-install    Install the browser the end-to-end tests need"
	@echo "  make typecheck      Type-check the frontend"
	@echo "  make generate-dto   Regenerate frontend DTOs from the backend schema"
	@echo "  make check-real-deq Run the conformance check against a real unit (needs hardware)"
	@echo "  make clean          Remove build artifacts and local databases"

install: install-backend install-frontend warm

install-backend:
	cd backend && uv sync

install-frontend:
	cd frontend && npm install

dev:
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) dev-backend & \
	$(MAKE) dev-frontend & \
	wait

dev-backend:
	cd backend && PYTHONPATH=. uv run uvicorn app.main:app --reload --port $(BACKEND_PORT)

dev-frontend:
	cd frontend && npm run dev -- --port $(FRONTEND_PORT)

# Fills the frontend's dependency cache without starting a server. The
# ttsc transform writes imports of typia's deep internals, so without this
# Vite discovers them on the first page load, re-optimizes and reloads.
# `make install` runs it. Run it again after a typia or vite change.
warm:
	cd frontend && npm run warm

# The whole stack against a DEQ whose answers are yours to change. This is
# the one to use for frontend work: `make dev` runs the plain fake, which
# always answers the same way. Run `make console` in a third terminal.
dev-sim:
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) dev-simulator & \
	$(MAKE) dev-frontend & \
	wait

# Only the backend, for when the frontend is already running elsewhere.
dev-simulator:
	cd backend && PYTHONPATH=. DEQ_TRANSPORT=simulator \
		uv run uvicorn app.main:app --reload --port $(BACKEND_PORT)

console:
	cd backend && uv run python scripts/deq_console.py

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest && uv run pytest ../pi-gadget

test-frontend:
	cd frontend && npm test

e2e-install:
	cd frontend && npx playwright install --with-deps chromium

e2e:
	cd frontend && npx playwright test

typecheck:
	cd frontend && npx tsc --noEmit

generate-dto:
	cd backend && PYTHONPATH=. uv run python scripts/export_openapi.py
	cd frontend && npm run generate:dto

# Needs a real DEQ. DEQ_TRANSPORT picks the link:
#   make check-real-deq                       the Pi's accessory gadget
#   make check-real-deq DEQ_TRANSPORT=usb     a unit on this machine's port
DEQ_TRANSPORT ?= accessory

check-real-deq:
	cd backend && PYTHONPATH=. DEQ_TRANSPORT=$(DEQ_TRANSPORT) \
		uv run python scripts/check_real_deq.py

clean:
	rm -f backend/deq.db
	rm -f backend/deq-simulator-state.json
	rm -rf backend/.venv
	rm -rf frontend/node_modules
