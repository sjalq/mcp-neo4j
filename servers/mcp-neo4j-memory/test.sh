#!/bin/bash

# Load environment from .env file if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Set defaults if not already set
export NEO4J_URI=${NEO4J_URI:-neo4j://localhost:7687}
export NEO4J_USERNAME=${NEO4J_USERNAME:-neo4j}
export NEO4J_PASSWORD=${NEO4J_PASSWORD:-password}

# Force CPU-only mode for testing to avoid CUDA issues
export FORCE_CPU=1

uv run pytest tests/test_neo4j_memory_integration.py
