from neo4j import AsyncDriver
from common.neo4j.read import execute_read_query
import pytest
from typing import Any

@pytest.mark.asyncio(loop_scope="session")
async def test_execute_read_query_with_parameters(async_neo4j_driver: AsyncDriver, healthcheck: Any, init_data: Any):

    query = """
    MATCH (p:Person)-[:FRIEND]->(friend)
    RETURN p.name AS person, friend.name AS friend_name
    ORDER BY p.name, friend.name
    """


    result = await execute_read_query(async_neo4j_driver, query)

    assert len(result) == 2
    assert result[0]["person"] == "Alice"
    assert result[0]["friend_name"] == "Bob"
    assert result[1]["person"] == "Bob"
    assert result[1]["friend_name"] == "Charlie"