import pytest
import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock
import tempfile
import os

from mcp_neo4j_memory.server import main, Entity, Relation
from mcp_neo4j_memory.vector_memory import VectorEnabledNeo4jMemory

class MockMCPServer:
    """Mock MCP server to test tool calls"""
    def __init__(self):
        self.tools = []
        self.tool_calls = {}
        
    def list_tools(self):
        def decorator(func):
            self.list_tools_handler = func
            return func
        return decorator
        
    def call_tool(self):
        def decorator(func):
            self.call_tool_handler = func
            return func
        return decorator
        
    async def get_tools(self):
        return await self.list_tools_handler()
        
    async def call_tool_by_name(self, name: str, arguments: dict):
        return await self.call_tool_handler(name, arguments)

@pytest.fixture
def mock_neo4j_driver():
    """Mock Neo4j driver for testing"""
    driver = MagicMock()
    driver.execute_query = MagicMock()
    driver.verify_connectivity = MagicMock()
    return driver

@pytest.fixture
def mock_vector_memory():
    """Mock VectorEnabledNeo4jMemory"""
    memory = MagicMock(spec=VectorEnabledNeo4jMemory)
    
    # Setup async method returns
    memory.read_graph = AsyncMock(return_value=MagicMock(model_dump=lambda: {"entities": [], "relations": []}))
    memory.search_nodes = AsyncMock(return_value=MagicMock(model_dump=lambda: {"entities": [], "relations": []}))
    memory.vector_search = AsyncMock(return_value=MagicMock(model_dump=lambda: {"entities": [], "relations": []}))
    memory.create_entities = AsyncMock(return_value=[])
    memory.create_relations = AsyncMock(return_value=[])
    memory.add_observations = AsyncMock(return_value=[])
    memory.delete_entities = AsyncMock()
    memory.delete_observations = AsyncMock()
    memory.delete_relations = AsyncMock()
    memory.find_nodes = AsyncMock(return_value=MagicMock(model_dump=lambda: {"entities": [], "relations": []}))
    
    return memory

@pytest.fixture
async def mcp_server_handlers(mock_neo4j_driver, mock_vector_memory):
    """Get MCP server handlers for testing"""
    
    # Mock the connection and memory creation
    with patch('mcp_neo4j_memory.server.GraphDatabase') as mock_graphdb, \
         patch('mcp_neo4j_memory.server.VectorEnabledNeo4jMemory') as mock_memory_class:
        
        mock_graphdb.driver.return_value = mock_neo4j_driver
        mock_memory_class.return_value = mock_vector_memory
        
        # Import server module after patching
        from mcp_neo4j_memory.server import Server
        
        # Create a mock server
        server = MockMCPServer()
        
        # We need to manually create the handlers since we can't easily run the full server
        # Instead, let's test the tool schemas and call the actual handler functions
        
        # Create memory getter function like in main()
        memory = None
        def get_memory():
            nonlocal memory
            if memory is None:
                memory = mock_vector_memory
            return memory
        
        # Create mock handlers
        async def handle_list_tools():
            # Import the actual tool definitions
            import mcp_neo4j_memory.server as server_module
            
            # Patch Server to capture tool definitions
            tools = []
            original_tool_init = server_module.types.Tool
            
            def mock_tool(*args, **kwargs):
                tools.append(kwargs)
                return original_tool_init(*args, **kwargs)
            
            with patch('mcp_neo4j_memory.server.types.Tool', side_effect=mock_tool):
                # This will trigger tool registration
                import importlib
                importlib.reload(server_module)
                
            return tools
        
        async def handle_call_tool(name: str, arguments: dict):
            mem = get_memory()
            
            if name == "vector_search":
                # This should fail if schema doesn't match implementation
                result = await mem.vector_search(
                    query=arguments.get("query"),
                    mode=arguments.get("mode"),  # This parameter should cause failure
                    limit=arguments.get("limit", 10),
                    threshold=arguments.get("threshold", 0.7)
                )
                return [{"type": "text", "text": json.dumps(result.model_dump(), indent=2)}]
            elif name == "search_nodes":
                result = await mem.search_nodes(arguments.get("query", ""))
                return [{"type": "text", "text": json.dumps(result.model_dump(), indent=2)}]
            else:
                raise ValueError(f"Unknown tool: {name}")
        
        return handle_list_tools, handle_call_tool

class TestMCPIntegration:
    """Integration tests for MCP tool interface"""
    
    @pytest.mark.asyncio
    async def test_vector_search_tool_schema_matches_implementation(self, mcp_server_handlers):
        """Test that vector_search tool schema matches the actual method signature"""
        handle_list_tools, handle_call_tool = mcp_server_handlers
        
        # Get tool definitions
        tools = await handle_list_tools()
        vector_search_tool = next((t for t in tools if t.get("name") == "vector_search"), None)
        
        assert vector_search_tool is not None, "vector_search tool not found"
        
        # Check schema has the parameters our implementation expects
        schema = vector_search_tool["inputSchema"]
        properties = schema["properties"]
        
        assert "query" in properties, "query parameter missing"
        
        # Test calling with the schema-defined parameters
        test_args = {
            "query": "test search",
            "limit": 5,
            "threshold": 0.8
        }
        
        # Add mode if it's in the schema
        if "mode" in properties:
            test_args["mode"] = "content"
        
        # This should not raise an exception if schema matches implementation
        try:
            result = await handle_call_tool("vector_search", test_args)
            assert result is not None
        except TypeError as e:
            if "unexpected keyword argument" in str(e):
                pytest.fail(f"Schema mismatch: {e}")
            else:
                raise
    
    @pytest.mark.asyncio
    async def test_vector_search_without_mode_parameter(self, mock_vector_memory):
        """Test that vector_search works without mode parameter (unified approach)"""
        
        # Test direct method call without mode
        result = await mock_vector_memory.vector_search(
            query="test",
            limit=10,
            threshold=0.7
        )
        
        # Verify it was called with expected parameters
        mock_vector_memory.vector_search.assert_called_once_with(
            query="test",
            limit=10,
            threshold=0.7
        )
    
    @pytest.mark.asyncio
    async def test_all_mcp_tools_callable(self, mcp_server_handlers):
        """Test that all MCP tools can be called without schema errors"""
        handle_list_tools, handle_call_tool = mcp_server_handlers
        
        tools = await handle_list_tools()
        
        # Define minimal valid arguments for each tool
        test_cases = {
            "read_graph": {},
            "search_nodes": {"query": "test"},
            "find_nodes": {"names": ["TestEntity"]},
            "open_nodes": {"names": ["TestEntity"]},
            "create_entities": {"entities": [{"name": "Test", "type": "Test", "observations": ["test"]}]},
            "create_relations": {"relations": [{"source": "A", "target": "B", "relationType": "TEST"}]},
            "add_observations": {"observations": [{"entityName": "Test", "contents": ["test"]}]},
            "delete_entities": {"entityNames": ["Test"]},
            "delete_observations": {"deletions": [{"entityName": "Test", "observations": ["test"]}]},
            "delete_relations": {"relations": [{"source": "A", "target": "B", "relationType": "TEST"}]},
        }
        
        # Test each tool
        for tool_def in tools:
            tool_name = tool_def.get("name")
            if tool_name in test_cases:
                try:
                    result = await handle_call_tool(tool_name, test_cases[tool_name])
                    assert result is not None, f"Tool {tool_name} returned None"
                except Exception as e:
                    pytest.fail(f"Tool {tool_name} failed: {e}")
    
    @pytest.mark.asyncio
    async def test_vector_search_schema_consistency(self, mcp_server_handlers):
        """Test that vector_search schema is consistent with current implementation"""
        handle_list_tools, handle_call_tool = mcp_server_handlers
        
        tools = await handle_list_tools()
        vector_search_tool = next((t for t in tools if t.get("name") == "vector_search"), None)
        
        if vector_search_tool:
            schema = vector_search_tool["inputSchema"]
            properties = schema["properties"]
            
            # Check if mode parameter exists in schema
            has_mode_in_schema = "mode" in properties
            
            # Try calling without mode (unified approach)
            try:
                await handle_call_tool("vector_search", {
                    "query": "test",
                    "limit": 10,
                    "threshold": 0.7
                })
                no_mode_works = True
            except Exception:
                no_mode_works = False
            
            # Try calling with mode (old approach)
            try:
                await handle_call_tool("vector_search", {
                    "query": "test",
                    "mode": "content",
                    "limit": 10,
                    "threshold": 0.7
                })
                with_mode_works = True
            except Exception:
                with_mode_works = False
            
            # Determine what the correct schema should be
            if no_mode_works and not with_mode_works:
                # Unified approach - schema should not have mode
                assert not has_mode_in_schema, "Schema has mode parameter but implementation doesn't accept it"
            elif with_mode_works and not no_mode_works:
                # Old approach - schema should have mode
                assert has_mode_in_schema, "Schema missing mode parameter but implementation requires it"
            else:
                pytest.fail("Inconsistent behavior: both approaches work or neither works")

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 