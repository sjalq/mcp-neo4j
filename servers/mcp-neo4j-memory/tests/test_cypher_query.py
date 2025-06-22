import pytest
import json
from unittest.mock import Mock, AsyncMock, MagicMock
from mcp_neo4j_memory.vector_memory import VectorEnabledNeo4jMemory


class TestCypherQuery:
    """Test cases for execute_cypher functionality"""

    def create_mock_summary(self):
        """Helper to create a properly mocked summary object"""
        mock_summary = Mock()
        mock_counters = Mock()
        mock_counters.nodes_created = 0
        mock_counters.nodes_deleted = 0
        mock_counters.relationships_created = 0
        mock_counters.relationships_deleted = 0
        mock_counters.properties_set = 0
        mock_counters.labels_added = 0
        mock_counters.labels_removed = 0
        mock_counters.indexes_added = 0
        mock_counters.indexes_removed = 0
        mock_counters.constraints_added = 0
        mock_counters.constraints_removed = 0
        mock_summary.counters = mock_counters
        mock_summary.database = "test_db"
        mock_summary.query_type = "r"
        mock_summary.result_consumed_after = 100
        mock_summary.result_available_after = 50
        return mock_summary

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver"""
        driver = Mock()
        driver._database = "test_db"
        return driver

    @pytest.fixture
    def memory(self, mock_driver):
        """Create a VectorEnabledNeo4jMemory instance with mocked dependencies"""
        # Mock embedding model loading
        with pytest.MonkeyPatch.context() as m:
            m.setattr("mcp_neo4j_memory.vector_memory.SentenceTransformer", Mock)
            m.setattr("mcp_neo4j_memory.vector_memory.torch.cuda.is_available", lambda: False)
            
            # Mock the index creation methods to avoid database calls during test setup
            # This will handle the fulltext and vector index creation calls
            mock_driver.execute_query.return_value = Mock()
            
            memory = VectorEnabledNeo4jMemory(mock_driver, auto_migrate=False)
            
            # Reset the mock after initialization so we can test the actual calls
            mock_driver.reset_mock()
            return memory

    @pytest.mark.asyncio
    async def test_basic_query_execution(self, memory, mock_driver):
        """Test basic Cypher query execution"""
        # Mock result
        mock_record = Mock()
        mock_record.keys.return_value = ["n"]
        mock_record.__getitem__ = lambda self, key: {"name": "test_node", "type": "TestType"}
        
        mock_result = Mock()
        mock_result.records = [mock_record]
        mock_result.summary = self.create_mock_summary()
        
        mock_driver.execute_query.return_value = mock_result
        
        # Execute query
        result = await memory.execute_cypher("MATCH (n) RETURN n LIMIT 1")
        
        # Verify result structure
        assert "records" in result
        assert "summary" in result
        assert len(result["records"]) == 1
        assert result["summary"]["database"] == "test_db"
        
        # Verify driver was called correctly
        mock_driver.execute_query.assert_called_once_with(
            "MATCH (n) RETURN n LIMIT 1",
            {}
        )

    @pytest.mark.asyncio
    async def test_query_with_parameters(self, memory, mock_driver):
        """Test Cypher query with parameters"""
        # Mock result
        mock_record = Mock()
        mock_record.keys.return_value = ["n"]
        mock_record.__getitem__ = lambda self, key: {"name": "John", "type": "Person"}
        
        mock_result = Mock()
        mock_result.records = [mock_record]
        mock_result.summary = self.create_mock_summary()
        
        mock_driver.execute_query.return_value = mock_result
        
        # Execute query with parameters
        params = {"name": "John"}
        result = await memory.execute_cypher("MATCH (n {name: $name}) RETURN n", params)
        
        # Verify result
        assert "records" in result
        assert len(result["records"]) == 1
        
        # Verify driver was called with parameters
        mock_driver.execute_query.assert_called_once_with(
            "MATCH (n {name: $name}) RETURN n",
            {"name": "John"}
        )

    @pytest.mark.asyncio
    async def test_query_error_handling(self, memory, mock_driver):
        """Test error handling for invalid queries"""
        # Mock error
        mock_driver.execute_query.side_effect = Exception("Invalid syntax")
        
        # Execute invalid query
        result = await memory.execute_cypher("INVALID CYPHER QUERY")
        
        # Verify error response
        assert "error" in result
        assert "query" in result
        assert result["error"] == "Invalid syntax"
        assert result["query"] == "INVALID CYPHER QUERY"

    @pytest.mark.asyncio
    async def test_empty_result_handling(self, memory, mock_driver):
        """Test handling of empty query results"""
        # Mock empty result
        mock_result = Mock()
        mock_result.records = []
        mock_result.summary = self.create_mock_summary()
        
        mock_driver.execute_query.return_value = mock_result
        
        # Execute query
        result = await memory.execute_cypher("MATCH (n:NonExistent) RETURN n")
        
        # Verify empty result
        assert "records" in result
        assert "summary" in result
        assert len(result["records"]) == 0
        assert result["summary"]["database"] == "test_db"

    @pytest.mark.asyncio
    async def test_node_properties_serialization(self, memory, mock_driver):
        """Test proper serialization of Neo4j nodes"""
        # Mock node with properties
        mock_node = Mock()
        mock_node._properties = {"name": "TestNode", "type": "Entity"}
        mock_node.labels = ["Entity", "TestLabel"]
        mock_node.id = 123
        
        mock_record = Mock()
        mock_record.keys.return_value = ["node"]
        mock_record.__getitem__ = lambda self, key: mock_node
        
        mock_result = Mock()
        mock_result.records = [mock_record]
        mock_result.summary = self.create_mock_summary()
        
        mock_driver.execute_query.return_value = mock_result
        
        # Execute query
        result = await memory.execute_cypher("MATCH (node:Entity) RETURN node")
        
        # Verify node serialization
        assert len(result["records"]) == 1
        node_data = result["records"][0]["node"]
        assert node_data["name"] == "TestNode"
        assert node_data["type"] == "Entity"
        assert node_data["_labels"] == ["Entity", "TestLabel"]
        assert node_data["_id"] == 123

    @pytest.mark.asyncio
    async def test_relationship_serialization(self, memory, mock_driver):
        """Test proper serialization of Neo4j relationships"""
        # Mock relationship with proper hasattr responses
        mock_rel = Mock()
        mock_rel._properties = {"weight": 0.8}
        mock_rel.type = "KNOWS"
        mock_rel.id = 456
        
        # Mock hasattr checks - relationship should NOT have 'labels' but should have 'type'
        def mock_hasattr(obj, attr):
            if attr == '_properties':
                return True
            if attr == 'labels':
                return False  # Relationships don't have labels
            if attr == 'type':
                return True  # Relationships have type
            return False
        
        mock_record = Mock()
        mock_record.keys.return_value = ["rel"]
        mock_record.__getitem__ = lambda self, key: mock_rel
        
        mock_result = Mock()
        mock_result.records = [mock_record]
        mock_result.summary = self.create_mock_summary()
        
        mock_driver.execute_query.return_value = mock_result
        
        # Patch hasattr to work with our mock
        with pytest.MonkeyPatch.context() as m:
            m.setattr("builtins.hasattr", mock_hasattr)
            
            # Execute query
            result = await memory.execute_cypher("MATCH ()-[rel:KNOWS]->() RETURN rel")
            
            # Verify relationship serialization
            assert len(result["records"]) == 1
            rel_data = result["records"][0]["rel"]
            assert rel_data["weight"] == 0.8
            assert rel_data["_type"] == "KNOWS"
            assert rel_data["_id"] == 456

    @pytest.mark.asyncio
    async def test_list_handling(self, memory, mock_driver):
        """Test handling of lists in query results"""
        # Mock list with nodes
        mock_node1 = Mock()
        mock_node1._properties = {"name": "Node1"}
        mock_node1.labels = ["Entity"]
        
        mock_node2 = Mock()
        mock_node2._properties = {"name": "Node2"}
        mock_node2.labels = ["Entity"]
        
        mock_record = Mock()
        mock_record.keys.return_value = ["nodes"]
        mock_record.__getitem__ = lambda self, key: [mock_node1, mock_node2]
        
        mock_result = Mock()
        mock_result.records = [mock_record]
        mock_result.summary = self.create_mock_summary()
        
        mock_driver.execute_query.return_value = mock_result
        
        # Execute query
        result = await memory.execute_cypher("MATCH (n:Entity) RETURN collect(n) as nodes")
        
        # Verify list handling
        assert len(result["records"]) == 1
        nodes_list = result["records"][0]["nodes"]
        assert len(nodes_list) == 2
        assert nodes_list[0]["name"] == "Node1"
        assert nodes_list[1]["name"] == "Node2" 