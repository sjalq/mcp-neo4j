# Generic Cypher Query Tool Implementation Plan

A simple implementation plan to add a generalized query tool to the Neo4j memory MCP server, similar to how the postgres query tool works.

## Overview
Add the ability to execute raw Cypher queries against the Neo4j database, providing maximum flexibility while maintaining the module's simplicity.

## Implementation Steps

### 1. Server Configuration (server.py)

- [ ] **Add Query Tool Definition** (~15 lines)
  - Location: `servers/mcp-neo4j-memory/src/mcp_neo4j_memory/server.py`
  - Function: `handle_list_tools()`
  - Add new tool definition:
    ```python
    types.Tool(
        name="execute_cypher",
        description="Execute a raw Cypher query on the knowledge graph database",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The Cypher query to execute"},
                "params": {
                    "type": "object",
                    "description": "Optional parameters for the query",
                    "additionalProperties": True
                }
            },
            "required": ["query"],
        },
    )
    ```

- [ ] **Add Query Handler** (~6 lines)
  - Location: Same file, `handle_call_tool()` function
  - Add new case:
    ```python
    elif name == "execute_cypher":
        query = arguments.get("query", "")
        params = arguments.get("params", {})
        result = await mem.execute_cypher(query, params)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    ```

### 2. Core Implementation (vector_memory.py)

- [ ] **Implement Query Method** (~20 lines)
  - Location: `servers/mcp-neo4j-memory/src/mcp_neo4j_memory/vector_memory.py`
  - Class: `VectorEnabledNeo4jMemory`
  - Add method:
    ```python
    async def execute_cypher(self, query: str, params: dict = None) -> dict:
        """Execute a raw Cypher query with minimal processing"""
        try:
            result = self.neo4j_driver.execute_query(
                query, 
                params or {},
                database_=self.neo4j_driver._database
            )
            
            # Convert to serializable format
            return {
                "records": [dict(record) for record in result.records],
                "summary": {
                    "counters": dict(result.summary.counters),
                    "database": result.summary.database.name if result.summary.database else None
                }
            }
        except Exception as e:
            logger.error(f"Cypher query error: {e}")
            return {"error": str(e), "query": query}
    ```

### 3. Optional Safety Features

- [ ] **Add Read-Only Mode Validator** (Optional - ~8 lines)
  - Can be added to vector_memory.py or as a utility
  - Simple function:
    ```python
    def is_read_only_query(query: str) -> bool:
        """Check if query only contains read operations"""
        write_keywords = ["CREATE", "MERGE", "DELETE", "SET", "REMOVE"]
        query_upper = query.upper()
        return not any(keyword in query_upper for keyword in write_keywords)
    ```

### 4. Testing

- [ ] **Create Test File**
  - Location: `servers/mcp-neo4j-memory/tests/test_cypher_query.py`
  - Test cases:
    - [ ] Basic query execution
    - [ ] Query with parameters
    - [ ] Error handling (invalid syntax)
    - [ ] Result serialization
    - [ ] Empty result handling

- [ ] **Manual Testing Script**
  - Create `test_cypher_manual.py` for quick validation
  - Test queries:
    ```cypher
    # Read all nodes
    MATCH (n) RETURN n LIMIT 10
    
    # Query with parameters
    MATCH (n:Entity {name: $name}) RETURN n
    
    # Complex query
    MATCH (n)-[r]->(m) RETURN n.name, type(r), m.name
    ```

### 5. Documentation

- [ ] **Update README**
  - Add example usage of `execute_cypher` tool
  - Include warning about direct query access

## Estimated Effort
- Total new code: ~50 lines
- Files modified: 2 (+ test files)
- Complexity: Low (reuses existing infrastructure)

## Notes
- This implementation provides full Cypher query capability
- Maintains consistency with existing tool patterns
- No new dependencies required
- Compatible with existing vector search functionality 