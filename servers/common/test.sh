docker compose -f tests/integration/docker-compose.yml up -d
uv run pytest tests/integration -s 
docker compose -f tests/integration/docker-compose.yml stop