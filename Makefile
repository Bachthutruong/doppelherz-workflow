# Doppelherz Content Robot — lệnh thường dùng. Chạy `make help` để xem danh sách.
PY       ?= python3.11
VENV     ?= .venv
BIN      := $(VENV)/bin
DATA_DIR ?= data/demo
PORT     ?= 8000

.PHONY: help install test lint demo serve docker-up docker-down clean

help: ## Liệt kê các lệnh
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Tạo môi trường ảo và cài đặt (kèm công cụ dev)
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e ".[dev]"

test: ## Chạy bộ kiểm thử
	$(BIN)/pytest

lint: ## Kiểm tra chất lượng mã (ruff)
	$(BIN)/ruff check src tests scripts

demo: ## Nạp kịch bản demo trên bài thật của doppelherz.vn
	DATA_DIR=$(DATA_DIR) $(BIN)/python scripts/demo_scenario.py

serve: ## Chạy dashboard tại http://127.0.0.1:$(PORT)
	DATA_DIR=$(DATA_DIR) $(BIN)/content-robot serve --port $(PORT)

docker-up: ## Chạy robot + n8n bằng Docker Compose
	docker compose up -d --build

docker-down: ## Dừng Docker Compose
	docker compose down

clean: ## Xóa môi trường ảo và tệp tạm
	rm -rf $(VENV) .pytest_cache .ruff_cache build dist src/*.egg-info
