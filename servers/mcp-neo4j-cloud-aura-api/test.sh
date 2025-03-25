uv run pytest tests/test_aura_manager.py
if [ -f .env ]; then
    uv run --env-file .env pytest tests/test_aura_integration.py
fi
