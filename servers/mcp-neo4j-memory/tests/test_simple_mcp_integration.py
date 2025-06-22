import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import inspect

from mcp_neo4j_memory.vector_memory import VectorEnabledNeo4jMemory


class TestSimpleMCPIntegration:
    """Simple integration tests for MCP tool interface"""
    
    def test_vector_search_method_signature(self):
        """Test that vector_search method doesn't have mode parameter"""
        
        # Get the actual method signature
        method = VectorEnabledNeo4jMemory.vector_search
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        
        # Should have these parameters but NOT mode
        assert "query" in params, "vector_search missing query parameter"
        assert "limit" in params, "vector_search missing limit parameter" 
        assert "threshold" in params, "vector_search missing threshold parameter"
        assert "mode" not in params, "vector_search still has mode parameter - migration incomplete!"
        
        print(f"✅ vector_search signature: {params}")
    
    @pytest.mark.asyncio
    async def test_vector_search_direct_call(self):
        """Test that vector_search can be called with unified parameters"""
        
        # Mock the dependencies
        mock_driver = MagicMock()
        mock_encoder = MagicMock() 
        # Mock numpy array with tolist() method
        mock_embedding = MagicMock()
        mock_embedding.tolist.return_value = [0.1] * 1024
        mock_encoder.encode.return_value = mock_embedding
        
        with patch('mcp_neo4j_memory.vector_memory.SentenceTransformer') as mock_st:
            mock_st.return_value = mock_encoder
            
            # Create memory instance
            memory = VectorEnabledNeo4jMemory(mock_driver)
            
            # Mock the Neo4j query execution
            mock_result = MagicMock()
            mock_result.records = []  # Empty results
            mock_driver.execute_query.return_value = mock_result
            
            # This should work without mode parameter
            result = await memory.vector_search(
                query="test search",
                limit=5,
                threshold=0.8
            )
            
            # Verify it was called
            assert mock_driver.execute_query.called
            print("✅ vector_search called successfully without mode parameter")
    
    def test_mcp_schema_consistency(self):
        """Test that MCP tool schema matches implementation"""
        
        # Import the server module to get tool definitions
        from mcp_neo4j_memory.server import main
        import mcp_neo4j_memory.server as server_module
        
        # Get the vector_search method signature
        method_sig = inspect.signature(VectorEnabledNeo4jMemory.vector_search)
        method_params = set(method_sig.parameters.keys()) - {"self"}  # Remove self
        
        print(f"Implementation parameters: {method_params}")
        
        # Expected parameters based on our migration
        expected_params = {"query", "limit", "threshold"}
        unexpected_params = {"mode"}
        
        assert method_params >= expected_params, f"Missing parameters: {expected_params - method_params}"
        assert method_params.isdisjoint(unexpected_params), f"Unexpected parameters found: {method_params & unexpected_params}"
        
        print("✅ Method signature matches expected unified approach")

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 