import json
import logging
from typing import Any, Optional

import mcp.types as types
from common import (
    cypher_validation,
    execute_read_query,
    execute_write_query,
    neo4j_healthcheck_for_mcp_server,
)
from mcp.server.fastmcp import FastMCP
from neo4j import (
    AsyncDriver,
    AsyncGraphDatabase,
)
from pydantic import Field

logger = logging.getLogger("mcp_neo4j_cypher")


def create_mcp_server(neo4j_driver: AsyncDriver, database: str = "neo4j") -> FastMCP:
    """
    Create a MCP server that is capable of executing read and write Cypher queries against a Neo4j database.

    Parameters
    ----------
    neo4j_driver: AsyncDriver
        The neo4j driver to use.
    database: str, optional
        The database to use, by default "neo4j"

    Returns
    -------
    FastMCP
        The MCP server.
    """

    mcp: FastMCP = FastMCP("mcp-neo4j-cypher", dependencies=["neo4j", "pydantic"])

    async def get_neo4j_schema() -> list[types.TextContent]:
        """List all node, their attributes and their relationships to other nodes in the neo4j database"""

        get_schema_query = """
call apoc.meta.data() yield label, property, type, other, unique, index, elementType
where elementType = 'node' and not label starts with '_'
with label, 
    collect(case when type <> 'RELATIONSHIP' then [property, type + case when unique then " unique" else "" end + case when index then " indexed" else "" end] end) as attributes,
    collect(case when type = 'RELATIONSHIP' then [property, head(other)] end) as relationships
RETURN label, apoc.map.fromPairs(attributes) as attributes, apoc.map.fromPairs(relationships) as relationships
"""

        result = await execute_read_query(
            neo4j_driver, get_schema_query, dict(), database, logger, False
        )
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    async def read_neo4j_cypher(
        query: str = Field(..., description="The Cypher query to execute."),
        params: Optional[dict[str, Any]] = Field(
            None, description="The parameters to pass to the Cypher query."
        ),
    ) -> list[types.TextContent]:
        """Execute a read Cypher query on the neo4j database."""

        if cypher_validation.is_write_query(query):
            raise ValueError("Only MATCH queries are allowed for read-query")

        result = await execute_read_query(
            neo4j_driver, query, params, database, logger, False
        )
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    async def write_neo4j_cypher(
        query: str = Field(..., description="The Cypher query to execute."),
        params: Optional[dict[str, Any]] = Field(
            None, description="The parameters to pass to the Cypher query."
        ),
    ) -> list[types.TextContent]:
        """Execute a write Cypher query on the neo4j database."""

        if not cypher_validation.is_write_query(query):
            raise ValueError("Only write queries are allowed for write-query")

        result = await execute_write_query(
            neo4j_driver, query, params, database, logger, False
        )
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    mcp.add_tool(get_neo4j_schema)
    mcp.add_tool(read_neo4j_cypher)
    mcp.add_tool(write_neo4j_cypher)

    return mcp


def main(
    db_url: str,
    username: str,
    password: str,
    database: str,
) -> None:
    logger.info("Starting MCP neo4j Server")

    neo4j_driver = AsyncGraphDatabase.driver(
        db_url,
        auth=(
            username,
            password,
        ),
    )

    mcp = create_mcp_server(neo4j_driver, database)

    neo4j_healthcheck_for_mcp_server(neo4j_driver, database)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
