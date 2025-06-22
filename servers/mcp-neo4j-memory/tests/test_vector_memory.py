import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import numpy as np

from mcp_neo4j_memory.vector_memory import VectorEnabledNeo4jMemory
from mcp_neo4j_memory.server import Entity, Relation

@pytest.fixture
def mock_neo4j_driver():
    """Mock Neo4j driver for testing"""
    driver = MagicMock()
    driver.execute_query = MagicMock()
    return driver

@pytest.fixture
def mock_encoder():
    """Mock sentence transformer encoder"""
    encoder = MagicMock()
    encoder.encode = MagicMock(return_value=np.random.rand(1024))
    encoder.max_seq_length = 512
    return encoder

@pytest.fixture
def memory_with_mocks(mock_neo4j_driver, mock_encoder):
    """VectorEnabledNeo4jMemory with mocked dependencies"""
    with patch('mcp_neo4j_memory.vector_memory.SentenceTransformer', return_value=mock_encoder):
        memory = VectorEnabledNeo4jMemory(mock_neo4j_driver, auto_migrate=False)
        return memory

class TestVectorEnabledNeo4jMemory:
    
    def test_initialization(self, mock_neo4j_driver):
        """Test proper initialization of vector memory system"""
        with patch('mcp_neo4j_memory.vector_memory.SentenceTransformer') as mock_st:
            mock_encoder = MagicMock()
            mock_st.return_value = mock_encoder
            
            memory = VectorEnabledNeo4jMemory(mock_neo4j_driver, auto_migrate=False)
            
            # Check model loading (account for device parameter)
            args, kwargs = mock_st.call_args
            assert args[0] == "BAAI/bge-large-en-v1.5"
            assert 'device' in kwargs  # May be 'cuda' or 'cpu' depending on system
            assert memory.encoder == mock_encoder
            assert memory.encoder.max_seq_length == 512
    
    def test_generate_embeddings(self, memory_with_mocks):
        """Test single unified embedding generation"""
        entity = Entity(
            name="Cyril Ramaphosa",
            type="Person", 
            observations=["Is president of South Africa", "Stashed cash in couch"]
        )
        
        embeddings = memory_with_mocks._generate_embeddings(entity)
        
        # Check single embedding is generated
        assert "embedding" in embeddings
        assert len(embeddings) == 1  # Only one embedding now
        
        # Check encoder was called once (not three times)
        assert memory_with_mocks.encoder.encode.call_count == 1
        
        # Verify content composition includes all context
        call_content = memory_with_mocks.encoder.encode.call_args[0][0]
        assert "Cyril Ramaphosa is a Person" in call_content
        assert "Is president of South Africa" in call_content
        assert "Stashed cash in couch" in call_content

    @pytest.mark.asyncio
    async def test_create_entities_with_embeddings(self, memory_with_mocks):
        """Test entity creation includes single embedding generation"""
        entities = [
            Entity(name="Cyril", type="Person", observations=["President"]),
            Entity(name="South Africa", type="Country", observations=["Has president"])
        ]
        
        # Mock successful database response
        memory_with_mocks.neo4j_driver.execute_query.return_value = MagicMock()
        
        result = await memory_with_mocks.create_entities(entities)
        
        # Check embeddings were generated (1 per entity now)
        assert memory_with_mocks.encoder.encode.call_count == 2  # 1 per entity
        
        # Check database query was called
        assert memory_with_mocks.neo4j_driver.execute_query.call_count >= 1
        
        # Core functionality test - embeddings were generated
        assert result == entities
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_vector_search_unified(self, memory_with_mocks):
        """Test unified vector search without modes"""
        # Mock database response
        mock_result = MagicMock()
        mock_result.records = [MagicMock()]
        mock_result.records[0].get.side_effect = lambda key, default=None: {
            'nodes': [{'name': 'Cyril', 'type': 'Person', 'observations': ['President']}],
            'relations': []
        }.get(key, default)
        
        memory_with_mocks.neo4j_driver.execute_query.return_value = mock_result
        
        # Test unified search (no mode parameter)
        result = await memory_with_mocks.vector_search("who is president")
        
        # Check encoder was called for query
        memory_with_mocks.encoder.encode.assert_called()
        
        # Check correct single index was used
        call_args = memory_with_mocks.neo4j_driver.execute_query.call_args[0][0]
        assert "entity_embeddings" in call_args
        
        # Ensure old index names are not used
        assert "entity_content_embeddings" not in call_args
        assert "entity_observation_embeddings" not in call_args
        assert "entity_identity_embeddings" not in call_args

    @pytest.mark.asyncio
    async def test_smart_search_simplified(self, memory_with_mocks):
        """Test simplified smart search routing"""
        
        # Mock methods
        memory_with_mocks.find_nodes = AsyncMock(return_value=MagicMock(entities=[]))
        memory_with_mocks.vector_search = AsyncMock()
        
        # Short query → should try exact match first
        await memory_with_mocks.smart_search("Cyril")
        memory_with_mocks.find_nodes.assert_called_once()
        
        # Long query → should use unified vector search (no mode parameter)
        memory_with_mocks.find_nodes.reset_mock()
        await memory_with_mocks.smart_search("what is the capital of South Africa?")
        memory_with_mocks.vector_search.assert_called_with("what is the capital of South Africa?", limit=10)

    @pytest.mark.asyncio
    async def test_migration_functionality(self, memory_with_mocks):
        """Test migration of existing unindexed memories"""
        
        # Mock unindexed memories exist
        mock_result = MagicMock()
        mock_record1 = MagicMock()
        mock_record1.__getitem__ = lambda self, key: {"name": "Cyril", "type": "Person", "observations": ["President"]}[key]
        mock_record2 = MagicMock()
        mock_record2.__getitem__ = lambda self, key: {"name": "SA", "type": "Country", "observations": ["Country"]}[key]
        mock_result.records = [mock_record1, mock_record2]
        
        memory_with_mocks.neo4j_driver.execute_query.return_value = mock_result
        
        await memory_with_mocks.migrate_existing_memories()
        
        # Check update query was called
        assert memory_with_mocks.neo4j_driver.execute_query.call_count >= 2
        
        # Check embeddings were generated during migration (1 per entity)
        assert memory_with_mocks.encoder.encode.call_count >= 2

    @pytest.mark.asyncio
    async def test_ensure_all_indexed(self, memory_with_mocks):
        """Test automatic indexing check on startup"""
        
        # Mock migration
        memory_with_mocks.migrate_existing_memories = AsyncMock()
        
        # First call returns count, second call is for migration
        count_record = MagicMock()
        count_record.__getitem__ = lambda self, k: 5 if k == "unindexed_count" else None
        memory_with_mocks.neo4j_driver.execute_query.side_effect = [
            MagicMock(records=[count_record]),  # count result
            MagicMock(records=[])  # migration result
        ]
        
        await memory_with_mocks.ensure_all_indexed()
        
        # Check migration was called
        memory_with_mocks.migrate_existing_memories.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_observations_updates_embeddings(self, memory_with_mocks):
        """Test that adding observations updates single embedding"""
        
        from mcp_neo4j_memory.server import ObservationAddition
        
        observations = [ObservationAddition(
            entityName="Cyril",
            contents=["New observation about leadership"]
        )]
        
        # Mock database responses
        entity_record = MagicMock()
        entity_record.__getitem__ = lambda self, k: {
            "name": "Cyril", 
            "type": "Person", 
            "observations": ["President", "New observation about leadership"]
        }[k]
        
        memory_with_mocks.neo4j_driver.execute_query.side_effect = [
            MagicMock(records=[]),  # add observations result
            MagicMock(records=[entity_record]),  # entity query result
            MagicMock(records=[])   # update embeddings result
        ]
        
        await memory_with_mocks.add_observations(observations)
        
        # Check single embedding was regenerated
        assert memory_with_mocks.encoder.encode.call_count == 1
        
        # Check update query was executed
        assert memory_with_mocks.neo4j_driver.execute_query.call_count >= 3

    def test_vector_index_creation(self, memory_with_mocks):
        """Test single vector index is created correctly"""
        
        # Check that _ensure_vector_indexes was called during init
        expected_calls = len(memory_with_mocks.neo4j_driver.execute_query.call_args_list)
        
        # Should have created fulltext + 1 vector index
        assert expected_calls >= 2
        
        # Check vector index creation queries
        calls = memory_with_mocks.neo4j_driver.execute_query.call_args_list
        vector_calls = [call for call in calls if "CREATE VECTOR INDEX" in str(call)]
        
        assert len(vector_calls) == 1  # Only one index now

    @pytest.mark.asyncio
    async def test_batch_processing(self, memory_with_mocks):
        """Test that large entity batches are processed efficiently"""
        
        # Create 50 entities (more than batch size of 16)
        entities = [
            Entity(name=f"Entity{i}", type="Test", observations=[f"Observation {i}"])
            for i in range(50)
        ]
        
        memory_with_mocks.neo4j_driver.execute_query.return_value = MagicMock()
        
        await memory_with_mocks.create_entities(entities)
        
        # Check embeddings were generated for all entities (1 per entity)
        assert memory_with_mocks.encoder.encode.call_count == 50  # 1 per entity

    @pytest.mark.asyncio 
    async def test_relation_context_embeddings(self, memory_with_mocks):
        """Test that relations get context embeddings"""
        
        relations = [Relation(
            source="Cyril",
            target="South Africa", 
            relationType="IS_PRESIDENT_OF"
        )]
        
        memory_with_mocks.neo4j_driver.execute_query.return_value = MagicMock()
        
        await memory_with_mocks.create_relations(relations)
        
        # Check context embedding was generated
        encoder_calls = [call[0][0] for call in memory_with_mocks.encoder.encode.call_args_list]
        assert "Cyril IS_PRESIDENT_OF South Africa" in encoder_calls

    @pytest.mark.asyncio
    async def test_search_fallback_to_fulltext(self, memory_with_mocks):
        """Test fallback to fulltext search when vector search fails"""
        
        # Mock vector search failure
        memory_with_mocks.smart_search = AsyncMock(side_effect=Exception("Vector search failed"))
        memory_with_mocks.load_graph = AsyncMock(return_value=MagicMock(entities=[]))
        
        result = await memory_with_mocks.search_nodes("test query")
        
        # Check fallback was used
        memory_with_mocks.load_graph.assert_called_once_with("test query")

    def test_embedding_dimensions_configuration(self, memory_with_mocks):
        """Test that embedding dimensions are correctly configured"""
        
        from mcp_neo4j_memory.config import EMBEDDING_DIMENSIONS
        
        # Should be 1024 for BGE-large
        assert EMBEDDING_DIMENSIONS == 1024
        
        # Check vector index creation uses correct dimensions
        calls = memory_with_mocks.neo4j_driver.execute_query.call_args_list
        vector_calls = [str(call) for call in calls if "CREATE VECTOR INDEX" in str(call)]
        
        for call in vector_calls:
            assert "1024" in call

    @pytest.mark.asyncio
    async def test_duplicate_entity_relationship_handling(self, memory_with_mocks):
        """Test that relationships work correctly even with duplicate entity names"""
        
        relations = [Relation(
            source="DuplicateEntity",
            target="AnotherEntity", 
            relationType="CONNECTS_TO"
        )]
        
        # Mock successful database response
        memory_with_mocks.neo4j_driver.execute_query.return_value = MagicMock()
        
        # This should not raise an exception even if there are duplicate entities
        result = await memory_with_mocks.create_relations(relations)
        
        # Check that the relation creation succeeded
        assert result == relations
        
        # Check that the query includes LIMIT 1 clauses to handle duplicates
        call_args = memory_with_mocks.neo4j_driver.execute_query.call_args[0][0]
        assert "LIMIT 1" in call_args
        
        # Should have two LIMIT 1 clauses (one for source, one for target)
        limit_count = call_args.count("LIMIT 1")
        assert limit_count == 2
        
        # Check that WITH clauses are used properly
        assert "WITH from LIMIT 1" in call_args
        assert "WITH from, to LIMIT 1" in call_args

# Benchmark tests for performance monitoring
class TestVectorMemoryPerformance:
    
    @pytest.mark.benchmark
    @pytest.mark.asyncio
    async def test_embedding_generation_performance(self, memory_with_mocks, benchmark):
        """Benchmark single embedding generation speed"""
        
        entity = Entity(
            name="Test Entity",
            type="TestType",
            observations=["Long observation text " * 20]  # Simulate longer content
        )
        
        # Benchmark the embedding generation
        result = benchmark(memory_with_mocks._generate_embeddings, entity)
        
        assert "embedding" in result
        assert len(result["embedding"]) == 1024

    @pytest.mark.benchmark
    @pytest.mark.asyncio 
    async def test_batch_creation_performance(self, memory_with_mocks, benchmark):
        """Benchmark batch entity creation performance"""
        
        entities = [
            Entity(name=f"Entity{i}", type="Test", observations=[f"Obs {i}"])
            for i in range(100)
        ]
        
        memory_with_mocks.neo4j_driver.execute_query.return_value = MagicMock()
        
        # Benchmark batch creation
        result = benchmark.pedantic(
            memory_with_mocks.create_entities,
            args=(entities,),
            rounds=3,
            iterations=1
        )

# Integration tests (require actual Neo4j instance)
@pytest.mark.integration
class TestVectorMemoryIntegration:
    
    @pytest.mark.skip(reason="Requires Neo4j instance")
    @pytest.mark.asyncio
    async def test_end_to_end_vector_workflow(self):
        """Test complete workflow with real Neo4j instance"""
        
        # This test would require:
        # 1. Real Neo4j connection
        # 2. Real BGE-large model download
        # 3. End-to-end entity creation and search
        
        pass

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 