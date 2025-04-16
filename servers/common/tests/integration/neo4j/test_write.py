from common.neo4j.write import execute_write_query
import pytest
from neo4j import AsyncDriver
from typing import Any

@pytest.mark.asyncio(loop_scope="session")
async def test_execute_write_query_with_parameters(async_neo4j_driver: AsyncDriver, healthcheck: Any):
    result = await execute_write_query(async_neo4j_driver, "MERGE (n:Person {name: $name}) RETURN n", {"name": "John"})

    assert len(result) == 4
    assert result["nodes_created"] == 1
    assert result["labels_added"] == 1
    assert result["properties_set"] == 1

@pytest.mark.asyncio(loop_scope="session")
async def test_execute_write_query_raise_error(async_neo4j_driver: AsyncDriver, healthcheck: Any) -> None:
    with pytest.raises(Exception):
        await execute_write_query(async_neo4j_driver, "UPSERT (n:Person {name: $name}) RETURN n", {"name": "John"}, raise_on_error=True)