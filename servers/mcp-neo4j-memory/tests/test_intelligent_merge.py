import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from mcp_neo4j_memory.vector_memory import VectorEnabledNeo4jMemory
from mcp_neo4j_memory.server import Entity, Relation

# Mock the encoder globally
mock_encoder = Mock()
mock_encoder.encode.return_value = Mock()
mock_encoder.encode.return_value.tolist.return_value = [0.1] * 1024

@pytest.fixture
def mock_neo4j_driver():
    driver = Mock()
    driver.execute_query = Mock()
    return driver

@pytest.fixture
def vector_memory(mock_neo4j_driver):
    # Patch the encoder import in the module
    import mcp_neo4j_memory.vector_memory as vm
    vm.SentenceTransformer = Mock(return_value=mock_encoder)
    
    memory = VectorEnabledNeo4jMemory(mock_neo4j_driver, auto_migrate=False)
    return memory

@pytest.mark.asyncio
class TestIntelligentMerge:
    """Test that entities with same names but different labels merge correctly"""
    
    async def test_same_name_different_labels_merge(self, vector_memory, mock_neo4j_driver):
        """Test that Ethereum with different labels merges into one entity"""
        
        # First entity: Ethereum with Blockchain + Technology labels
        entity1 = Entity(
            name="Ethereum",
            type="Technology",
            observations=["Smart contract platform"],
            labels=["Blockchain", "Technology"]
        )
        
        # Second entity: Ethereum with Digital + Platform labels  
        entity2 = Entity(
            name="Ethereum", 
            type="Technology",
            observations=["Supports DeFi applications"],
            labels=["Digital", "Platform"]
        )
        
        # Create first entity
        await vector_memory.create_entities([entity1])
        
        # Verify the MERGE query structure for first entity (skip index creation calls)
        calls = mock_neo4j_driver.execute_query.call_args_list
        merge_calls = [call for call in calls if "MERGE" in str(call)]
        assert len(merge_calls) > 0, "No MERGE queries found"
        merge_call = merge_calls[0]
        
        # Should MERGE by name and type only
        merge_query = merge_call[0][0]
        
        assert "MERGE (e { name: $name, type: $type })" in merge_query
        assert "ON CREATE SET e:Entity" in merge_query
        assert "ON MATCH SET e:Entity" in merge_query
        
        # Should have label addition calls
        label_calls = [call for call in calls if "SET e:Blockchain" in str(call) or "SET e:Technology" in str(call)]
        assert len(label_calls) == 2
        
        # Reset mock for second entity
        mock_neo4j_driver.execute_query.reset_mock()
        
        # Create second entity (should merge)
        await vector_memory.create_entities([entity2])
        
        # Verify second entity merges correctly
        calls = mock_neo4j_driver.execute_query.call_args_list
        merge_calls = [call for call in calls if "MERGE" in str(call)]
        assert len(merge_calls) > 0, "No MERGE queries found for second entity"
        merge_call = merge_calls[0]
        
        merge_query = merge_call[0][0]
        
        # Should still MERGE by name and type
        assert "MERGE (e { name: $name, type: $type })" in merge_query
        assert "ON MATCH SET e:Entity" in merge_query
        
        # Should combine observations
        assert "e.observations + [obs in $observations WHERE NOT obs IN e.observations]" in merge_query
        
        # Should add new labels
        label_calls = [call for call in calls if "SET e:Digital" in str(call) or "SET e:Platform" in str(call)]
        assert len(label_calls) == 2

    async def test_different_names_no_merge(self, vector_memory, mock_neo4j_driver):
        """Test that entities with different names don't merge"""
        
        entity1 = Entity(
            name="Bitcoin",
            type="Technology", 
            observations=["Digital currency"],
            labels=["Blockchain"]
        )
        
        entity2 = Entity(
            name="Ethereum",
            type="Technology",
            observations=["Smart contracts"],
            labels=["Blockchain"]
        )
        
        await vector_memory.create_entities([entity1, entity2])
        
        # Should have separate MERGE calls for each entity
        calls = mock_neo4j_driver.execute_query.call_args_list
        merge_calls = [call for call in calls if "MERGE" in str(call[0][0])]
        
        assert len(merge_calls) == 2
        
        # Verify each has different name
        names = [call[0][1]["name"] for call in merge_calls]
        assert "Bitcoin" in names
        assert "Ethereum" in names

    async def test_same_name_different_type_no_merge(self, vector_memory, mock_neo4j_driver):
        """Test entities with same name but different types don't merge"""
        
        entity1 = Entity(
            name="Apple",
            type="Company",
            observations=["Tech company"],
            labels=["Technology"]
        )
        
        entity2 = Entity(
            name="Apple", 
            type="Fruit",
            observations=["Red fruit"],
            labels=["Food"]
        )
        
        await vector_memory.create_entities([entity1, entity2])
        
        # Should have separate MERGE calls 
        calls = mock_neo4j_driver.execute_query.call_args_list
        merge_calls = [call for call in calls if "MERGE" in str(call[0][0])]
        
        assert len(merge_calls) == 2
        
        # Verify different types
        types = [call[0][1]["type"] for call in merge_calls]
        assert "Company" in types
        assert "Fruit" in types

    async def test_observation_merging(self, vector_memory, mock_neo4j_driver):
        """Test that observations merge correctly without duplicates"""
        
        # First entity with some observations
        entity1 = Entity(
            name="Python",
            type="ProgrammingLanguage",
            observations=["Easy to learn", "Great for beginners"],
            labels=["Programming"]
        )
        
        # Second entity with overlapping observations
        entity2 = Entity(
            name="Python",
            type="ProgrammingLanguage", 
            observations=["Great for beginners", "Used in AI"],  # "Great for beginners" is duplicate
            labels=["AI"]
        )
        
        # Create entities
        await vector_memory.create_entities([entity1])
        mock_neo4j_driver.execute_query.reset_mock()
        
        await vector_memory.create_entities([entity2])
        
        # Check the ON MATCH query handles observation deduplication
        calls = mock_neo4j_driver.execute_query.call_args_list
        merge_calls = [call for call in calls if "MERGE" in str(call)]
        assert len(merge_calls) > 0, "No MERGE queries found"
        merge_call = merge_calls[0]
        merge_query = merge_call[0][0]
        
        # Should have deduplication logic
        assert "e.observations + [obs in $observations WHERE NOT obs IN e.observations]" in merge_query

    async def test_relations_work_after_merge(self, vector_memory, mock_neo4j_driver):
        """Test that relations work correctly after entity merging"""
        
        # Create entities
        entity1 = Entity(name="Alice", type="Person", observations=["Developer"], labels=["Professional"])
        entity2 = Entity(name="Bob", type="Person", observations=["Manager"], labels=["Leadership"])
        
        await vector_memory.create_entities([entity1, entity2])
        mock_neo4j_driver.execute_query.reset_mock()
        
        # Create relation
        relation = Relation(source="Alice", target="Bob", relationType="WORKS_WITH")
        await vector_memory.create_relations([relation])
        
        # Verify relation creation uses Entity label with duplicate handling
        calls = mock_neo4j_driver.execute_query.call_args_list
        relation_call = calls[0]
        relation_query = relation_call[0][0]
        
        assert "MATCH (from:Entity {name: $source})" in relation_query
        assert "WITH from LIMIT 1" in relation_query
        assert "MATCH (to:Entity {name: $target})" in relation_query
        assert "WITH from, to LIMIT 1" in relation_query
        assert "MERGE (from)-[r:WORKS_WITH]->(to)" in relation_query

    async def test_no_memory_label_anywhere(self, vector_memory, mock_neo4j_driver):
        """Test that Memory label is completely removed from the system"""
        
        entity = Entity(
            name="TestEntity",
            type="Test",
            observations=["Test observation"],
            labels=["TestLabel"]
        )
        
        await vector_memory.create_entities([entity])
        
        # Check all queries for Memory label
        all_calls = mock_neo4j_driver.execute_query.call_args_list
        for call in all_calls:
            query = str(call[0][0])
            assert ":Memory" not in query, f"Found Memory label in query: {query}"
            assert "Memory" not in query or "Memory" in ["VectorEnabledNeo4jMemory", "memory"], f"Unexpected Memory reference: {query}"

    async def test_entity_base_label_always_present(self, vector_memory, mock_neo4j_driver):
        """Test that Entity base label is always added"""
        
        entity = Entity(
            name="TestEntity", 
            type="Test",
            observations=["Test"],
            labels=["Custom"]
        )
        
        await vector_memory.create_entities([entity])
        
        calls = mock_neo4j_driver.execute_query.call_args_list
        merge_calls = [call for call in calls if "MERGE" in str(call)]
        assert len(merge_calls) > 0, "No MERGE queries found"
        merge_call = merge_calls[0]
        merge_query = merge_call[0][0]
        
        # Should set Entity label
        assert "SET e:Entity" in merge_query 