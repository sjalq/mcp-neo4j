"""Shared test configuration and utilities"""

import pytest
import asyncio
from neo4j import GraphDatabase
from mcp_neo4j_memory.vector_memory import VectorEnabledNeo4jMemory


def cleanup_test_entities(driver, entity_names=None, labels=None):
    """Clean up specific test entities by name or label"""
    if entity_names:
        name_conditions = " OR ".join([f"n.name = '{name}'" for name in entity_names])
        cleanup_query = f"""
        MATCH (n)
        WHERE {name_conditions}
        DETACH DELETE n
        """
    elif labels:
        label_conditions = " OR ".join([f"n:{label}" for label in labels])
        cleanup_query = f"""
        MATCH (n)
        WHERE {label_conditions}
        DETACH DELETE n
        """
    else:
        # Default cleanup for common test patterns
        cleanup_query = """
        MATCH (n)
        WHERE (n:Test OR n:TestGroup OR n:Character OR n:BatchTest OR n:SpecialTest OR n:Employee OR n:Manager OR n:Active OR n:Friend OR n:Tech OR n:Engineer OR n:Language)
        OR (n.name IS NOT NULL AND (
            n.name STARTS WITH 'Test' OR 
            n.name STARTS WITH 'Alice' OR 
            n.name STARTS WITH 'Bob' OR 
            n.name STARTS WITH 'Charlie' OR
            n.name STARTS WITH 'Dave' OR
            n.name STARTS WITH 'Eve' OR
            n.name STARTS WITH 'Frank' OR
            n.name STARTS WITH 'Grace' OR
            n.name STARTS WITH 'Hank' OR
            n.name STARTS WITH 'Ian' OR
            n.name STARTS WITH 'Jane' OR
            n.name STARTS WITH 'Kevin' OR
            n.name STARTS WITH 'Laura' OR
            n.name STARTS WITH 'Mike' OR
            n.name STARTS WITH 'Node' OR
            n.name STARTS WITH 'Concurrent' OR
            n.name STARTS WITH 'BatchEntity' OR
            n.name STARTS WITH 'TechPerson' OR
            n.name STARTS WITH 'BusinessPerson' OR
            n.name STARTS WITH 'LegacyChar' OR
            n.name STARTS WITH 'NewChar' OR
            n.name STARTS WITH 'Name' OR
            n.name CONTAINS 'with' OR
            n.name = 'Python' OR
            n.name = 'Project X'
        ))
        DETACH DELETE n
        """
    
    driver.execute_query(cleanup_query)


@pytest.fixture(autouse=True)
def cleanup_after_test(request):
    """Automatically cleanup test data after each test"""
    yield  # Run the test
    
    # Get the test's neo4j_driver fixture if it exists
    if hasattr(request, 'node') and hasattr(request.node, 'funcargs'):
        driver = request.node.funcargs.get('neo4j_driver')
        if driver:
            cleanup_test_entities(driver) 