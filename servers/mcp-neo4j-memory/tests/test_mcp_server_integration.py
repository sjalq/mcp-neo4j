import os
import pytest
import pytest_asyncio
import json
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from neo4j import GraphDatabase

import mcp.types as types
from mcp_neo4j_memory.server import main, Entity, Relation
from mcp_neo4j_memory.vector_memory import VectorEnabledNeo4jMemory
from mcp.server import Server

@pytest.fixture(scope="function")
def neo4j_driver():
    """Create a Neo4j driver for MCP server testing."""
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password123")
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        driver.verify_connectivity()
    except Exception as e:
        pytest.skip(f"Could not connect to Neo4j: {e}")
    
    # Clean up before tests - SAFE: Only delete test data with specific patterns
    cleanup_query = """
    MATCH (n)
    WHERE (n:Test OR n:TestGroup OR n:Character)
    OR (n.name IS NOT NULL AND (n.name STARTS WITH 'Test' OR n.name STARTS WITH 'Concurrent' OR n.name STARTS WITH 'Special' OR n.name STARTS WITH 'Alice' OR n.name STARTS WITH 'Bob' OR n.name STARTS WITH 'Entity' OR n.name STARTS WITH 'DataScientist' OR n.name STARTS WITH 'Designer' OR n.name STARTS WITH 'SpecificEntity' OR n.name STARTS WITH 'ProjectAlpha' OR n.name STARTS WITH 'Sarah'))
    DETACH DELETE n
    """
    driver.execute_query(cleanup_query)
    
    yield driver
    
    # Clean up after tests
    driver.execute_query(cleanup_query)
    driver.close()

@pytest_asyncio.fixture
async def mcp_server(neo4j_driver):
    """Create an MCP server instance for testing"""
    # Create server with mock streams
    server = Server("mcp-neo4j-memory")
    
    # Initialize memory 
    memory = VectorEnabledNeo4jMemory(neo4j_driver, auto_migrate=False)
    
    # Register handlers (simplified version of main())
    @server.list_tools()
    async def handle_list_tools():
        return [
            types.Tool(
                name="create_entities",
                description="Create multiple new entities in the knowledge graph",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {"type": "string"},
                                    "observations": {"type": "array", "items": {"type": "string"}},
                                    "labels": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3}
                                },
                                "required": ["name", "type", "observations", "labels"],
                            },
                        },
                    },
                    "required": ["entities"],
                }
            ),
            types.Tool(
                name="create_relations",
                description="Create multiple new relations between entities",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "relations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source": {"type": "string"},
                                    "target": {"type": "string"},
                                    "relationType": {"type": "string"}
                                },
                                "required": ["source", "target", "relationType"]
                            }
                        }
                    },
                    "required": ["relations"]
                }
            ),
            types.Tool(
                name="add_observations",
                description="Add new observations to existing entities",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "observations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "entityName": {"type": "string"},
                                    "contents": {"type": "array", "items": {"type": "string"}}
                                },
                                "required": ["entityName", "contents"]
                            }
                        }
                    },
                    "required": ["observations"]
                }
            ),
            types.Tool(
                name="search_nodes",
                description="Search for nodes in the knowledge graph",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    },
                    "required": ["query"]
                }
            ),
            types.Tool(
                name="find_nodes",
                description="Find specific nodes by names",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "names": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["names"]
                }
            ),
            types.Tool(
                name="read_graph",
                description="Read the entire knowledge graph",
                inputSchema={"type": "object", "properties": {}}
            )
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments):
        try:
            if name == "read_graph":
                result = await memory.read_graph()
                return [types.TextContent(type="text", text=json.dumps(result.model_dump(), indent=2))]
            
            elif name == "create_entities":
                entities = [Entity(**entity) for entity in arguments.get("entities", [])]
                result = await memory.create_entities(entities)
                return [types.TextContent(type="text", text=json.dumps([e.model_dump() for e in result], indent=2))]
                
            elif name == "create_relations":
                relations = [Relation(**relation) for relation in arguments.get("relations", [])]
                result = await memory.create_relations(relations)
                return [types.TextContent(type="text", text=json.dumps([r.model_dump() for r in result], indent=2))]
                
            elif name == "add_observations":
                from mcp_neo4j_memory.server import ObservationAddition
                observations = [ObservationAddition(**obs) for obs in arguments.get("observations", [])]
                result = await memory.add_observations(observations)
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                
            elif name == "search_nodes":
                result = await memory.search_nodes(arguments.get("query", ""))
                return [types.TextContent(type="text", text=json.dumps(result.model_dump(), indent=2))]
                
            elif name == "find_nodes":
                result = await memory.find_nodes(arguments.get("names", []))
                return [types.TextContent(type="text", text=json.dumps(result.model_dump(), indent=2))]
            
            else:
                raise ValueError(f"Unknown tool: {name}")
                
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]
    
    # Add helper method to simulate MCP call_tool behavior
    async def call_tool_helper(name: str, arguments: dict):
        return await handle_call_tool(name, arguments)
    
    # Add helper method to get tools list
    async def get_tools_list():
        return await handle_list_tools()
    
    server.call_tool_helper = call_tool_helper
    server.get_tools_list = get_tools_list
    return server

class TestMCPServerIntegration:
    """Test the MCP server layer that Agents actually interact with"""

    @pytest.mark.asyncio
    async def test_create_entities_mcp_json_flow(self, mcp_server):
        """Test create_entities through MCP server with JSON serialization"""
        
        # Prepare JSON input as Agent would send it
        agent_input = {
            "entities": [
                {
                    "name": "TestPerson", 
                    "type": "Person",
                    "observations": ["Observation 1", "Observation 2"],
                    "labels": ["Test", "Agent"]
                }
            ]
        }
        
        # Call MCP tool directly (simulating Agent call)
        response = await mcp_server.call_tool_helper("create_entities", agent_input)
        
        # Verify response format that Agent receives
        assert len(response) == 1
        assert isinstance(response[0], types.TextContent)
        
        # Parse JSON response
        response_data = json.loads(response[0].text)
        
        # Verify Agent gets expected data structure
        assert isinstance(response_data, list)
        assert len(response_data) == 1
        
        entity = response_data[0]
        assert entity["name"] == "TestPerson"
        assert entity["type"] == "Person"
        assert "Observation 1" in entity["observations"]
        assert "Observation 2" in entity["observations"]
        assert entity["labels"] == ["Test", "Agent"]  # Labels are returned in current implementation

    @pytest.mark.asyncio 
    async def test_read_graph_mcp_json_flow(self, mcp_server):
        """Test read_graph through MCP server with JSON serialization"""
        
        # First create some data through MCP
        create_input = {
            "entities": [
                {
                    "name": "Alice",
                    "type": "Person", 
                    "observations": ["Works remotely"],
                    "labels": ["Employee"]
                },
                {
                    "name": "Bob",
                    "type": "Person",
                    "observations": ["Team lead"], 
                    "labels": ["Manager"]
                }
            ]
        }
        
        await mcp_server.call_tool_helper("create_entities", create_input)
        
        # Read graph through MCP (no arguments needed)
        response = await mcp_server.call_tool_helper("read_graph", {})
        
        # Verify response format
        assert len(response) == 1
        assert isinstance(response[0], types.TextContent)
        
        # Parse JSON response  
        graph_data = json.loads(response[0].text)
        
        # Verify Agent gets expected data structure
        assert "entities" in graph_data
        assert "relations" in graph_data
        assert isinstance(graph_data["entities"], list)
        assert isinstance(graph_data["relations"], list)
        
        # Verify data content
        entity_names = [e["name"] for e in graph_data["entities"]]
        assert "Alice" in entity_names
        assert "Bob" in entity_names

    @pytest.mark.asyncio
    async def test_mcp_error_handling_invalid_input(self, mcp_server):
        """Test how MCP server handles invalid input that Agent might send"""
        
        # Test missing required field
        invalid_input = {
            "entities": [
                {
                    "name": "TestPerson",
                    # Missing required fields: type, observations, labels
                }
            ]
        }
        
        response = await mcp_server.call_tool_helper("create_entities", invalid_input)
        
        # Should return error message, not crash
        assert len(response) == 1
        assert isinstance(response[0], types.TextContent)
        assert "Error:" in response[0].text

    @pytest.mark.asyncio
    async def test_mcp_error_handling_malformed_json(self, mcp_server):
        """Test how MCP server handles malformed data structures"""
        
        # Test completely wrong structure
        invalid_input = {
            "wrong_key": "wrong_value"
        }
        
        response = await mcp_server.call_tool_helper("create_entities", invalid_input)
        
        # Should handle gracefully
        assert len(response) == 1
        assert isinstance(response[0], types.TextContent)
        # Should either work with empty list or return error
        
    @pytest.mark.asyncio 
    async def test_mcp_tool_list_functionality(self, mcp_server):
        """Test that MCP server properly lists available tools for Agent"""
        
        tools = await mcp_server.get_tools_list()
        
        # Verify tool list structure
        assert isinstance(tools, list)
        assert len(tools) >= 2  # At least create_entities and read_graph
        
        # Check create_entities tool
        create_tool = next((t for t in tools if t.name == "create_entities"), None)
        assert create_tool is not None
        assert create_tool.description
        assert create_tool.inputSchema
        
        # Verify schema has required structure for Agent
        schema = create_tool.inputSchema
        assert schema["type"] == "object"
        assert "entities" in schema["properties"]
        assert schema["properties"]["entities"]["type"] == "array"
        
        # Check read_graph tool
        read_tool = next((t for t in tools if t.name == "read_graph"), None)
        assert read_tool is not None
        assert read_tool.description

    @pytest.mark.asyncio
    async def test_mcp_json_serialization_edge_cases(self, mcp_server):
        """Test JSON serialization of edge cases Agent might encounter"""
        
        # Test entities with special characters
        special_input = {
            "entities": [
                {
                    "name": "Entity with 🚀 emoji and spaces",
                    "type": "Special",
                    "observations": ["Observation with 'quotes'", 'And "double quotes"'],
                    "labels": ["Unicode", "Test"]
                }
            ]
        }
        
        response = await mcp_server.call_tool_helper("create_entities", special_input)
        
        # Should handle special characters properly
        assert len(response) == 1
        response_data = json.loads(response[0].text)
        assert response_data[0]["name"] == "Entity with 🚀 emoji and spaces"

    @pytest.mark.asyncio
    async def test_mcp_large_data_handling(self, mcp_server):
        """Test MCP server with larger data sets Agent might send"""
        
        # Create larger batch
        large_input = {
            "entities": [
                {
                    "name": f"Entity{i}",
                    "type": "BatchTest",
                    "observations": [f"Observation {i}", f"Extra observation {i}"],
                    "labels": ["Batch", "Test"]
                } for i in range(50)  # Reasonable batch size
            ]
        }
        
        response = await mcp_server.call_tool_helper("create_entities", large_input)
        
        # Should handle larger batches
        assert len(response) == 1
        response_data = json.loads(response[0].text)
        assert len(response_data) == 50

    @pytest.mark.asyncio
    async def test_mcp_concurrent_agent_requests(self, mcp_server):
        """Test MCP server handling concurrent Agent requests"""
        
        # Simulate multiple Agent requests happening concurrently
        async def create_entity(i):
            input_data = {
                "entities": [
                    {
                        "name": f"ConcurrentEntity{i}",
                        "type": "Concurrent",
                        "observations": [f"Created by agent {i}"],
                        "labels": ["Concurrent", "Test"]
                    }
                ]
            }
            return await mcp_server.call_tool_helper("create_entities", input_data)
        
        # Run concurrent requests
        responses = await asyncio.gather(*[create_entity(i) for i in range(5)])
        
        # All should succeed
        assert len(responses) == 5
        for response in responses:
            assert len(response) == 1
            assert isinstance(response[0], types.TextContent)
            data = json.loads(response[0].text)
            assert len(data) == 1
        
        # Verify all entities were created
        graph_response = await mcp_server.call_tool_helper("read_graph", {})
        graph_data = json.loads(graph_response[0].text)
        concurrent_entities = [e for e in graph_data["entities"] if e["type"] == "Concurrent"]
        assert len(concurrent_entities) == 5

# Additional test for Agent workflow simulation
@pytest.mark.asyncio
async def test_realistic_agent_workflow(mcp_server):
    """Test a realistic Agent workflow using MCP tools"""
    
    # 1. Agent creates entities about a project
    project_data = {
        "entities": [
            {
                "name": "ProjectAlpha",
                "type": "Project", 
                "observations": ["Machine learning project", "Started in Q1"],
                "labels": ["Active", "ML"]
            },
            {
                "name": "Sarah",
                "type": "Person",
                "observations": ["Lead data scientist", "Python expert"],
                "labels": ["TeamMember", "Senior"]
            }
        ]
    }
    
    create_response = await mcp_server.call_tool_helper("create_entities", project_data)
    assert "Error:" not in create_response[0].text
    
    # 2. Agent reads back the graph to verify
    read_response = await mcp_server.call_tool_helper("read_graph", {})
    graph_data = json.loads(read_response[0].text)
    
    # 3. Agent verifies the data is as expected
    entity_names = [e["name"] for e in graph_data["entities"]]
    assert "ProjectAlpha" in entity_names
    assert "Sarah" in entity_names
    
    # 4. Agent can access specific entity data
    sarah = next(e for e in graph_data["entities"] if e["name"] == "Sarah")
    assert sarah["type"] == "Person"
    assert "Python expert" in sarah["observations"]
    
    # This simulates how an Agent would actually use the system
    
    @pytest.mark.asyncio
    async def test_create_relations_mcp_json_flow(self, mcp_server):
        """Test create_relations through MCP server"""
        
        # First create entities that relations will connect
        entities_input = {
            "entities": [
                {
                    "name": "Alice", 
                    "type": "Person",
                    "observations": ["Software engineer"],
                    "labels": ["Employee"]
                },
                {
                    "name": "Bob",
                    "type": "Person", 
                    "observations": ["Team lead"],
                    "labels": ["Manager"]
                }
            ]
        }
        await mcp_server.call_tool_helper("create_entities", entities_input)
        
        # Create relations through MCP
        relations_input = {
            "relations": [
                {
                    "source": "Alice",
                    "target": "Bob", 
                    "relationType": "REPORTS_TO"
                }
            ]
        }
        
        response = await mcp_server.call_tool_helper("create_relations", relations_input)
        
        # Verify response format
        assert len(response) == 1
        assert isinstance(response[0], types.TextContent)
        
        # Parse JSON response
        response_data = json.loads(response[0].text)
        
        # Verify Agent gets expected relation data
        assert isinstance(response_data, list)
        assert len(response_data) == 1
        
        relation = response_data[0]
        assert relation["source"] == "Alice"
        assert relation["target"] == "Bob"
        assert relation["relationType"] == "REPORTS_TO"

    @pytest.mark.asyncio
    async def test_add_observations_mcp_json_flow(self, mcp_server):
        """Test add_observations through MCP server"""
        
        # First create an entity
        entity_input = {
            "entities": [
                {
                    "name": "Charlie",
                    "type": "Person",
                    "observations": ["Initial observation"],
                    "labels": ["Test"]
                }
            ]
        }
        await mcp_server.call_tool_helper("create_entities", entity_input)
        
        # Add observations through MCP
        observations_input = {
            "observations": [
                {
                    "entityName": "Charlie",
                    "contents": ["New observation 1", "New observation 2"]
                }
            ]
        }
        
        response = await mcp_server.call_tool_helper("add_observations", observations_input)
        
        # Verify response format
        assert len(response) == 1
        assert isinstance(response[0], types.TextContent)
        
        # Parse JSON response
        response_data = json.loads(response[0].text)
        
        # Verify Agent gets expected structure
        assert isinstance(response_data, list)
        assert len(response_data) == 1

    @pytest.mark.asyncio
    async def test_search_nodes_mcp_json_flow(self, mcp_server):
        """Test search_nodes through MCP server"""
        
        # Create searchable entities
        entities_input = {
            "entities": [
                {
                    "name": "DataScientist",
                    "type": "Person",
                    "observations": ["Loves machine learning", "Python expert"], 
                    "labels": ["Tech"]
                },
                {
                    "name": "Designer", 
                    "type": "Person",
                    "observations": ["Creative professional", "UI/UX specialist"],
                    "labels": ["Creative"]
                }
            ]
        }
        await mcp_server.call_tool_helper("create_entities", entities_input)
        
        # Search through MCP
        search_input = {
            "query": "machine learning"
        }
        
        response = await mcp_server.call_tool_helper("search_nodes", search_input)
        
        # Verify response format
        assert len(response) == 1
        assert isinstance(response[0], types.TextContent)
        
        # Parse JSON response
        response_data = json.loads(response[0].text)
        
        # Verify Agent gets expected search structure
        assert "entities" in response_data
        assert "relations" in response_data
        assert isinstance(response_data["entities"], list)
        assert isinstance(response_data["relations"], list)

    @pytest.mark.asyncio
    async def test_find_nodes_mcp_json_flow(self, mcp_server):
        """Test find_nodes through MCP server"""
        
        # Create specific entities 
        entities_input = {
            "entities": [
                {
                    "name": "SpecificEntity1",
                    "type": "Test",
                    "observations": ["Test data 1"],
                    "labels": ["FindTest"]
                },
                {
                    "name": "SpecificEntity2",
                    "type": "Test", 
                    "observations": ["Test data 2"],
                    "labels": ["FindTest"]
                },
                {
                    "name": "SpecificEntity3",
                    "type": "Test",
                    "observations": ["Test data 3"],
                    "labels": ["FindTest"]
                }
            ]
        }
        await mcp_server.call_tool_helper("create_entities", entities_input)
        
        # Find specific nodes through MCP
        find_input = {
            "names": ["SpecificEntity1", "SpecificEntity3"]
        }
        
        response = await mcp_server.call_tool_helper("find_nodes", find_input)
        
        # Verify response format
        assert len(response) == 1
        assert isinstance(response[0], types.TextContent)
        
        # Parse JSON response
        response_data = json.loads(response[0].text)
        
        # Verify Agent gets expected structure
        assert "entities" in response_data
        assert "relations" in response_data
        
        # Verify only requested entities returned
        entity_names = [e["name"] for e in response_data["entities"]]
        assert "SpecificEntity1" in entity_names
        assert "SpecificEntity3" in entity_names
        assert "SpecificEntity2" not in entity_names 