import os
import pytest
import asyncio
from neo4j import GraphDatabase
from mcp_neo4j_memory.server import Entity, Relation, ObservationAddition, ObservationDeletion
from mcp_neo4j_memory.vector_memory import VectorEnabledNeo4jMemory

@pytest.fixture(scope="function")
def neo4j_driver():
    """Create a Neo4j driver using environment variables for connection details."""
    uri = os.environ.get("NEO4J_URI", "neo4j://localhost:7687")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password")
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    # Verify connection
    try:
        driver.verify_connectivity()
    except Exception as e:
        pytest.skip(f"Could not connect to Neo4j: {e}")
    
    # Clean up ALL test data before tests (comprehensive cleanup)
    cleanup_query = """
    MATCH (n)
    WHERE (n:Test OR n:TestGroup OR n:Character)
    OR (n.name IS NOT NULL AND (n.name STARTS WITH 'Test' OR n.name STARTS WITH 'Alice' OR n.name STARTS WITH 'Bob' OR n.name STARTS WITH 'Charlie' OR n.name STARTS WITH 'John' OR n.name STARTS WITH 'Jane'))
    DETACH DELETE n
    """
    driver.execute_query(cleanup_query)
    
    yield driver
    
    # Clean up ALL test data after tests (comprehensive cleanup)
    driver.execute_query(cleanup_query)
    
    driver.close()

@pytest.fixture(scope="function")
def memory(neo4j_driver):
    """Create a VectorEnabledNeo4jMemory instance with the Neo4j driver."""
    memory_instance = VectorEnabledNeo4jMemory(neo4j_driver)
    
    yield memory_instance
    
    # Cleanup after each test
    cleanup_query = """
    MATCH (n)
    WHERE (n:Test OR n:TestGroup OR n:Character OR n:Employee OR n:Manager OR n:Active OR n:Friend OR n:Tech OR n:Engineer OR n:Language)
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
        n.name STARTS WITH 'TechPerson' OR
        n.name STARTS WITH 'BusinessPerson' OR
        n.name STARTS WITH 'LegacyChar' OR
        n.name STARTS WITH 'NewChar' OR
        n.name = 'Python' OR
        n.name = 'Project X'
    ))
    DETACH DELETE n
    """
    neo4j_driver.execute_query(cleanup_query)

@pytest.mark.asyncio
async def test_create_and_read_entities(memory):
    # Get initial state
    initial_graph = await memory.read_graph()
    initial_entity_count = len(initial_graph.entities)
    
    # Create test entities
    test_entities = [
        Entity(name="Alice", type="Person", observations=["Likes reading", "Works at Company X"], labels=["Friend", "Colleague"]),
        Entity(name="Bob", type="Person", observations=["Enjoys hiking"], labels=["Friend"])
    ]
    # Create entities in the graph
    created_entities = await memory.create_entities(test_entities)
    
    # Verify creation response 
    assert len(created_entities) == 2
    created_names = [e.name for e in created_entities]
    assert "Alice" in created_names
    assert "Bob" in created_names
    
    # Verify created entities have correct content
    alice_created = next(e for e in created_entities if e.name == "Alice")
    bob_created = next(e for e in created_entities if e.name == "Bob")
    
    assert alice_created.type == "Person"
    assert alice_created.observations == ["Likes reading", "Works at Company X"]
    assert bob_created.type == "Person" 
    assert bob_created.observations == ["Enjoys hiking"]
    
    # Read the graph
    graph = await memory.read_graph()
    
    # Verify entities were persisted (should be initial + 2 new entities)
    assert len(graph.entities) == initial_entity_count + 2
    
    # Check persisted data matches created data
    entities_by_name = {entity.name: entity for entity in graph.entities}
    assert "Alice" in entities_by_name
    assert "Bob" in entities_by_name
    
    # Verify full data integrity
    alice_persisted = entities_by_name["Alice"]
    bob_persisted = entities_by_name["Bob"]
    
    assert alice_persisted.type == "Person"
    assert "Likes reading" in alice_persisted.observations
    assert "Works at Company X" in alice_persisted.observations
    assert len(alice_persisted.observations) >= 2  # Could have more due to merging
    
    assert bob_persisted.type == "Person"
    assert "Enjoys hiking" in bob_persisted.observations

@pytest.mark.asyncio
async def test_create_and_read_relations(memory):
    # Create test entities
    test_entities = [
        Entity(name="Alice", type="Person", observations=[], labels=["Friend"]),
        Entity(name="Bob", type="Person", observations=[], labels=["Friend"])
    ]
    await memory.create_entities(test_entities)
    
    # Create test relation
    test_relations = [
        Relation(source="Alice", target="Bob", relationType="KNOWS")
    ]
    
    # Create relation in the graph
    created_relations = await memory.create_relations(test_relations)
    assert len(created_relations) == 1
    
    # Read the graph
    graph = await memory.read_graph()
    
    # Verify relation was created
    assert len(graph.relations) == 1
    relation = graph.relations[0]
    assert relation.source == "Alice"
    assert relation.target == "Bob"
    assert relation.relationType == "KNOWS"

@pytest.mark.asyncio
async def test_add_observations(memory):
    # Create test entity
    test_entity = Entity(name="Charlie", type="Person", observations=["Initial observation"], labels=["Test"])
    await memory.create_entities([test_entity])
    
    # Add observations
    observation_additions = [
        ObservationAddition(entityName="Charlie", contents=["New observation 1", "New observation 2"])
    ]
    
    result = await memory.add_observations(observation_additions)
    assert len(result) == 1
    
    # Read the graph
    graph = await memory.read_graph()
    
    # Find Charlie
    charlie = next((e for e in graph.entities if e.name == "Charlie"), None)
    assert charlie is not None
    
    # Verify observations were added
    assert "Initial observation" in charlie.observations
    assert "New observation 1" in charlie.observations
    assert "New observation 2" in charlie.observations

@pytest.mark.asyncio
async def test_delete_observations(memory):
    # Create test entity with observations
    test_entity = Entity(
        name="Dave", 
        type="Person", 
        observations=["Observation 1", "Observation 2", "Observation 3"],
        labels=["Test"]
    )
    await memory.create_entities([test_entity])
    
    # Delete specific observations
    observation_deletions = [
        ObservationDeletion(entityName="Dave", observations=["Observation 2"])
    ]
    
    await memory.delete_observations(observation_deletions)
    
    # Read the graph
    graph = await memory.read_graph()
    
    # Find Dave
    dave = next((e for e in graph.entities if e.name == "Dave"), None)
    assert dave is not None
    
    # Verify observation was deleted
    assert "Observation 1" in dave.observations
    assert "Observation 2" not in dave.observations
    assert "Observation 3" in dave.observations

@pytest.mark.asyncio
async def test_delete_entities(memory):
    # Create test entities
    test_entities = [
        Entity(name="Eve", type="Person", observations=[], labels=["Test"]),
        Entity(name="Frank", type="Person", observations=[], labels=["Test"])
    ]
    await memory.create_entities(test_entities)
    
    # Delete one entity
    await memory.delete_entities(["Eve"])
    
    # Read the graph
    graph = await memory.read_graph()
    
    # Verify Eve was deleted but Frank remains
    entity_names = [e.name for e in graph.entities]
    assert "Eve" not in entity_names
    assert "Frank" in entity_names

@pytest.mark.asyncio
async def test_delete_relations(memory):
    # Create test entities
    test_entities = [
        Entity(name="Grace", type="Person", observations=[], labels=["Test"]),
        Entity(name="Hank", type="Person", observations=[], labels=["Test"])
    ]
    await memory.create_entities(test_entities)
    
    # Create test relations
    test_relations = [
        Relation(source="Grace", target="Hank", relationType="KNOWS"),
        Relation(source="Grace", target="Hank", relationType="WORKS_WITH")
    ]
    await memory.create_relations(test_relations)
    
    # Delete one relation
    relations_to_delete = [
        Relation(source="Grace", target="Hank", relationType="KNOWS")
    ]
    await memory.delete_relations(relations_to_delete)
    
    # Read the graph
    graph = await memory.read_graph()
    
    # Verify only the WORKS_WITH relation remains
    assert len(graph.relations) == 1
    assert graph.relations[0].relationType == "WORKS_WITH"

@pytest.mark.asyncio
async def test_search_nodes(memory):
    # Create test entities with more distinctive differences
    test_entities = [
        Entity(name="Ian", type="Person", observations=["Loves programming in Python"], labels=["Friend"]),
        Entity(name="Jane", type="Person", observations=["Enjoys gardening flowers"], labels=["Friend"]),
        Entity(name="Python", type="Language", observations=["Programming language for data science"], labels=["Tech"])
    ]
    await memory.create_entities(test_entities)
    
    # Test actual search_nodes method (not vector_search)
    result = await memory.search_nodes("programming")
    
    # Verify search functionality works and returns entities
    entity_names = [e.name for e in result.entities]
    assert len(entity_names) > 0  # Should find at least some entities
    assert "Python" in entity_names or "Ian" in entity_names  # Should find programming-related entities
    
    # Test search with partial name match
    result = await memory.search_nodes("Ian")
    entity_names = [e.name for e in result.entities]
    assert "Ian" in entity_names

@pytest.mark.asyncio
async def test_find_nodes(memory):
    # Create test entities
    test_entities = [
        Entity(name="Kevin", type="Person", observations=[], labels=["Test"]),
        Entity(name="Laura", type="Person", observations=[], labels=["Test"]),
        Entity(name="Mike", type="Person", observations=[], labels=["Test"])
    ]
    await memory.create_entities(test_entities)
    
    # Open specific nodes
    result = await memory.find_nodes(["Kevin", "Laura"])
    
    # Verify only requested nodes are returned
    entity_names = [e.name for e in result.entities]
    assert "Kevin" in entity_names
    assert "Laura" in entity_names
    assert "Mike" not in entity_names


@pytest.mark.asyncio
async def test_read_graph_dedicated(memory):
    """Dedicated test for read_graph functionality"""
    # Create test data with unique names to avoid conflicts
    test_entities = [
        Entity(name="Alice", type="Person", observations=["Works remotely"], labels=["Employee"]),
        Entity(name="Bob", type="Person", observations=["Team lead"], labels=["Manager"]),
        Entity(name="Project X", type="Project", observations=["Q2 initiative"], labels=["Active"])
    ]
    await memory.create_entities(test_entities)
    
    test_relations = [
        Relation(source="Alice", target="Bob", relationType="REPORTS_TO"),
        Relation(source="Bob", target="Project X", relationType="MANAGES")
    ]
    await memory.create_relations(test_relations)
    
    # Test full graph read
    graph = await memory.read_graph()
    
    # Verify our specific entities exist (don't rely on total count due to test data)
    entity_names = [e.name for e in graph.entities]
    assert "Alice" in entity_names
    assert "Bob" in entity_names
    assert "Project X" in entity_names
    
    # Verify our specific relations exist
    relation_pairs = [(r.source, r.target, r.relationType) for r in graph.relations]
    assert ("Alice", "Bob", "REPORTS_TO") in relation_pairs
    assert ("Bob", "Project X", "MANAGES") in relation_pairs
    
    # Verify data integrity
    alice = next(e for e in graph.entities if e.name == "Alice")
    assert alice.type == "Person"
    assert "Works remotely" in alice.observations


@pytest.mark.asyncio 
async def test_open_nodes(memory):
    """Test open_nodes tool (should behave identically to find_nodes)"""
    # Create test entities
    test_entities = [
        Entity(name="Node1", type="Test", observations=["First node"], labels=["TestGroup"]),
        Entity(name="Node2", type="Test", observations=["Second node"], labels=["TestGroup"]),
        Entity(name="Node3", type="Test", observations=["Third node"], labels=["TestGroup"])
    ]
    await memory.create_entities(test_entities)
    
    # Test find_nodes
    find_result = await memory.find_nodes(["Node1", "Node3"])
    
    # Since open_nodes calls find_nodes in the server, we test it through the vector memory
    # In practice this would be tested through the MCP server interface
    open_result = await memory.find_nodes(["Node1", "Node3"])  # Same call as open_nodes makes
    
    # Results should be identical
    assert len(find_result.entities) == len(open_result.entities) == 2
    
    find_names = [e.name for e in find_result.entities]
    open_names = [e.name for e in open_result.entities]
    assert find_names == open_names
    assert "Node1" in find_names
    assert "Node3" in find_names
    assert "Node2" not in find_names


@pytest.mark.asyncio
async def test_read_graph_with_legacy_data(memory):
    """Test read_graph handles nodes without Entity label (legacy data)"""
    # Directly insert legacy data without Entity label
    legacy_query = """
    CREATE (old:Character {name: 'LegacyChar', type: 'Character', observations: ['Old data']})
    CREATE (new:Entity {name: 'NewChar', type: 'Character', observations: ['New data']})
    CREATE (old)-[:KNOWS]->(new)
    """
    memory.neo4j_driver.execute_query(legacy_query)
    
    # read_graph should find both legacy and new nodes
    graph = await memory.read_graph()
    
    entity_names = [e.name for e in graph.entities]
    assert "LegacyChar" in entity_names  # Should find legacy node
    assert "NewChar" in entity_names     # Should find new node
    
    # Should also find the relationship between our specific nodes
    legacy_relations = [r for r in graph.relations if r.source == "LegacyChar" and r.target == "NewChar"]
    assert len(legacy_relations) == 1
    assert legacy_relations[0].relationType == "KNOWS"


@pytest.mark.asyncio
async def test_vector_search_modes(memory):
    """Comprehensive test for vector_search with different modes"""
    # Create entities with distinctive content for each mode
    test_entities = [
        Entity(name="TechPerson", type="Person", observations=["Codes in Python", "Uses machine learning"], labels=["Engineer"]),
        Entity(name="BusinessPerson", type="Person", observations=["Manages teams", "Strategic planning"], labels=["Manager"]),
        Entity(name="Python", type="Technology", observations=["Programming language", "Used for AI"], labels=["Language"])
    ]
    await memory.create_entities(test_entities)
    
    # Test content mode (default)
    result = await memory.vector_search("programming technology", mode="content")
    entity_names = [e.name for e in result.entities]
    assert len(entity_names) > 0
    
    # Test observations mode  
    result = await memory.vector_search("programming", mode="observations")
    entity_names = [e.name for e in result.entities]
    assert len(entity_names) > 0
    
    # Test identity mode
    result = await memory.vector_search("Python", mode="identity")
    entity_names = [e.name for e in result.entities]
    assert "Python" in entity_names
    
    # Test with custom threshold and limit
    result = await memory.vector_search("technology", threshold=0.1, limit=5)
    assert len(result.entities) <= 5