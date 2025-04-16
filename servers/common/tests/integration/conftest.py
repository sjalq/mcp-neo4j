import time
from typing import Any

import pytest
import pytest_asyncio
from neo4j import AsyncGraphDatabase, AsyncDriver, GraphDatabase, Driver
from neo4j.exceptions import DatabaseError

from mcp_neo4j_cypher.server import create_mcp_server
from common import neo4j_healthcheck_for_integration_tests


@pytest_asyncio.fixture(scope="session")
async def async_neo4j_driver():
    driver = AsyncGraphDatabase.driver(
        "neo4j://localhost:7687", auth=("neo4j", "testingpassword")
    )
    try:
        yield driver
    finally:
        await driver.close()


@pytest.fixture(scope="session")
def sync_neo4j_driver():
    uri = "neo4j://localhost:7687"
    auth = ("neo4j", "testingpassword")
    driver = GraphDatabase.driver(uri, auth=auth)
    yield driver
    driver.close()


@pytest.fixture(scope="session")
def healthcheck(sync_neo4j_driver: Driver):
    """Confirm that Neo4j is running before running IT."""

    neo4j_healthcheck_for_integration_tests(sync_neo4j_driver, "neo4j")
    yield


@pytest.fixture(scope="session")
def init_data(sync_neo4j_driver: Driver, clear_data: Any):
    with sync_neo4j_driver.session(database="neo4j") as session:
        session.run("CREATE (a:Person {name: 'Alice', age: 30})")
        session.run("CREATE (b:Person {name: 'Bob', age: 25})")
        session.run("CREATE (c:Person {name: 'Charlie', age: 35})")
        session.run(
            "MATCH (a:Person {name: 'Alice'}), (b:Person {name: 'Bob'}) CREATE (a)-[:FRIEND]->(b)"
        )
        session.run(
            "MATCH (b:Person {name: 'Bob'}), (c:Person {name: 'Charlie'}) CREATE (b)-[:FRIEND]->(c)"
        )


@pytest.fixture(scope="session")
def clear_data(sync_neo4j_driver: Driver):
    with sync_neo4j_driver.session(database="neo4j") as session:
        session.run("MATCH (n) DETACH DELETE n")
