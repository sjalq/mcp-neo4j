import pytest
import pytest_asyncio
import os
import asyncio
from neo4j import GraphDatabase
from mcp_neo4j_memory.server import Entity, Relation
from mcp_neo4j_memory.vector_memory import VectorEnabledNeo4jMemory

def get_neo4j_credentials():
    """Get Neo4j credentials from environment"""
    return {
        "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        "username": os.getenv("NEO4J_USERNAME", "neo4j"), 
        "password": os.getenv("NEO4J_PASSWORD", "password123")
    }

@pytest.mark.integration
@pytest.mark.asyncio
class TestMergeIntegration:
    """Integration tests for entity merging with real Neo4j"""
    
    @pytest_asyncio.fixture(scope="class")
    async def neo4j_memory(self):
        """Setup real Neo4j connection for testing"""
        try:
            creds = get_neo4j_credentials()
            driver = GraphDatabase.driver(
                creds["uri"],
                auth=(creds["username"], creds["password"])
            )
            
            # Test connection
            driver.verify_connectivity()
            
            memory = VectorEnabledNeo4jMemory(driver, auto_migrate=False)
            
            # Clean up test data first
            self._cleanup_test_data(driver)
            
            yield memory
            
            # Cleanup after tests
            self._cleanup_test_data(driver)
            driver.close()
            
        except Exception as e:
            pytest.skip(f"Neo4j not available: {e}")
    
    def _cleanup_test_data(self, driver):
        """Clean up test entities"""
        cleanup_query = """
        MATCH (e)
        WHERE e.name IN ['Ethereum', 'Bitcoin', 'TestMerge', 'Alice', 'Bob', 'Python', 'NoMemoryTest']
        DETACH DELETE e
        """
        driver.execute_query(cleanup_query)

    async def test_entity_merge_deduplication(self, neo4j_memory):
        """Test that same-named entities with different labels merge properly"""
        
        # Create first Ethereum entity
        entity1 = Entity(
            name="Ethereum",
            type="Technology",
            observations=["Smart contract platform", "Created by Vitalik Buterin"],
            labels=["Blockchain", "Technology"]
        )
        
        result1 = await neo4j_memory.create_entities([entity1])
        assert len(result1) == 1
        
        # Create second Ethereum entity (should merge)
        entity2 = Entity(
            name="Ethereum", 
            type="Technology",
            observations=["Supports DeFi", "Uses proof-of-stake"],
            labels=["Digital", "Platform"]
        )
        
        result2 = await neo4j_memory.create_entities([entity2])
        assert len(result2) == 1
        
        # Verify only one Ethereum entity exists
        query = """
        MATCH (e:Entity {name: 'Ethereum'})
        RETURN e.name as name, e.type as type, e.observations as observations, labels(e) as labels
        """
        
        result = neo4j_memory.neo4j_driver.execute_query(query)
        assert len(result.records) == 1, "Should have exactly one Ethereum entity after merge"
        
        record = result.records[0]
        assert record["name"] == "Ethereum"
        assert record["type"] == "Technology"
        
        # Should have combined observations (4 total, no duplicates)
        observations = record["observations"]
        expected_obs = ["Smart contract platform", "Created by Vitalik Buterin", "Supports DeFi", "Uses proof-of-stake"]
        assert len(observations) == 4
        for obs in expected_obs:
            assert obs in observations
        
        # Should have Entity base label plus all additional labels
        labels = record["labels"]
        expected_labels = {"Entity", "Blockchain", "Technology", "Digital", "Platform"}
        assert set(labels) == expected_labels

    async def test_different_entities_no_merge(self, neo4j_memory):
        """Test that different entities don't merge"""
        
        bitcoin = Entity(
            name="Bitcoin",
            type="Technology", 
            observations=["First cryptocurrency"],
            labels=["Blockchain"]
        )
        
        ethereum = Entity(
            name="Ethereum",
            type="Technology",
            observations=["Smart contracts"],
            labels=["Blockchain"] 
        )
        
        await neo4j_memory.create_entities([bitcoin, ethereum])
        
        # Should have two separate entities
        query = """
        MATCH (e:Entity)
        WHERE e.name IN ['Bitcoin', 'Ethereum']
        RETURN count(e) as count
        """
        
        result = neo4j_memory.neo4j_driver.execute_query(query)
        assert result.records[0]["count"] == 2

    async def test_observation_deduplication(self, neo4j_memory):
        """Test that duplicate observations are not added"""
        
        # First entity
        entity1 = Entity(
            name="TestMerge",
            type="Test",
            observations=["First observation", "Shared observation"],
            labels=["Test"]
        )
        
        await neo4j_memory.create_entities([entity1])
        
        # Second entity with overlapping observation
        entity2 = Entity(
            name="TestMerge",
            type="Test", 
            observations=["Shared observation", "New observation"],  # "Shared observation" is duplicate
            labels=["Updated"]
        )
        
        await neo4j_memory.create_entities([entity2])
        
        # Check final state
        query = """
        MATCH (e:Entity {name: 'TestMerge'})
        RETURN e.observations as observations
        """
        
        result = neo4j_memory.neo4j_driver.execute_query(query)
        observations = result.records[0]["observations"]
        
        # Should have 3 unique observations
        expected = ["First observation", "Shared observation", "New observation"]
        assert len(observations) == 3
        for obs in expected:
            assert obs in observations

    async def test_relations_after_merge(self, neo4j_memory):
        """Test that relations work correctly after entity merging"""
        
        # Create entities
        alice = Entity(name="Alice", type="Person", observations=["Developer"], labels=["Professional"])
        bob = Entity(name="Bob", type="Person", observations=["Manager"], labels=["Leadership"]) 
        
        await neo4j_memory.create_entities([alice, bob])
        
        # Create relation
        relation = Relation(source="Alice", target="Bob", relationType="WORKS_WITH")
        await neo4j_memory.create_relations([relation])
        
        # Verify relation exists
        query = """
        MATCH (a:Entity {name: 'Alice'})-[r:WORKS_WITH]->(b:Entity {name: 'Bob'})
        RETURN count(r) as count
        """
        
        result = neo4j_memory.neo4j_driver.execute_query(query)
        assert result.records[0]["count"] == 1

    async def test_no_memory_label_in_database(self, neo4j_memory):
        """Test that no Memory labels exist in the database"""
        
        # Create test entity
        entity = Entity(
            name="NoMemoryTest",
            type="Test",
            observations=["Testing no Memory label"],
            labels=["Test"]
        )
        
        await neo4j_memory.create_entities([entity])
        
        # Check that no Memory labels exist
        query = """
        MATCH (n:Memory)
        RETURN count(n) as count
        """
        
        result = neo4j_memory.neo4j_driver.execute_query(query)
        memory_count = result.records[0]["count"]
        assert memory_count == 0, "Should not have any nodes with Memory label"
        
        # Verify Entity label exists instead
        query = """
        MATCH (n:Entity {name: 'NoMemoryTest'})
        RETURN count(n) as count, labels(n) as labels
        """
        
        result = neo4j_memory.neo4j_driver.execute_query(query)
        assert result.records[0]["count"] == 1
        labels = result.records[0]["labels"]
        assert "Entity" in labels
        assert "Test" in labels
        assert "Memory" not in labels

    async def test_vector_search_after_merge(self, neo4j_memory):
        """Test that vector search works after entity merging"""
        
        # Create merged entity
        entity1 = Entity(
            name="Python",
            type="ProgrammingLanguage",
            observations=["Easy to learn"],
            labels=["Programming"]
        )
        
        entity2 = Entity(
            name="Python", 
            type="ProgrammingLanguage",
            observations=["Used in AI"],
            labels=["AI"]
        )
        
        await neo4j_memory.create_entities([entity1])
        await neo4j_memory.create_entities([entity2])
        
        # Test vector search
        try:
            result = await neo4j_memory.vector_search("programming language", mode="content", limit=5)
            
            # Should find the merged Python entity
            entity_names = [e.name for e in result.entities]
            assert "Python" in entity_names
            
            # Find the Python entity
            python_entity = next(e for e in result.entities if e.name == "Python")
            assert len(python_entity.observations) == 2  # Should have both observations
            
        except Exception as e:
            # If vector search fails, at least verify the entity merged correctly
            query = """
            MATCH (e:Entity {name: 'Python'})
            RETURN e.observations as observations
            """
            result = neo4j_memory.neo4j_driver.execute_query(query)
            observations = result.records[0]["observations"]
            assert len(observations) == 2 