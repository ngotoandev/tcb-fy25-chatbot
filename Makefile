.PHONY: ingest dev test evals
ingest:
	python -m ingest.run
dev:
	docker compose up --build
test:
	pytest
evals:
	pytest -m eval -q -s
