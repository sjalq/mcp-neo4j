import time
from typing import Any

import pytest
import pytest_asyncio
from neo4j import AsyncGraphDatabase, Driver, GraphDatabase
from neo4j.exceptions import DatabaseError

from mcp_neo4j_cypher.server import create_mcp_server


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

    print("Confirming Neo4j is running...")
    attempts = 0
    success = False
    print("\nWaiting for Neo4j to Start...\n")
    time.sleep(3)
    while not success and attempts < 3:
        try:
            print(f"Attempt {attempts + 1} to connect to Neo4j...")
            with sync_neo4j_driver.session(database="neo4j") as session:
                session.run("RETURN 1")
            success = True
            print("Neo4j is running!")
        except Exception as e:
            attempts += 1
            print(
                f"failed connection {attempts} | waiting {(1 + attempts) * 2} seconds..."
            )
            print(f"Error: {e}")
            time.sleep((1 + attempts) * 2)
    if not success:
        raise DatabaseError()
    yield


@pytest_asyncio.fixture(scope="session")
async def mcp_server(async_neo4j_driver):
    mcp = create_mcp_server(async_neo4j_driver, "neo4j")

    return mcp


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
