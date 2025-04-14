from . import server
import asyncio
import argparse
import os


def main():
    """Main entry point for the package."""
    parser = argparse.ArgumentParser(description="Neo4j Cypher MCP Server")
    parser.add_argument("--db-url", default=None, help="Neo4j connection URL")
    parser.add_argument("--username", default=None, help="Neo4j username")
    parser.add_argument("--password", default=None, help="Neo4j password")

    args = parser.parse_args()

    asyncio.run(
        server.main(
            args.db_url or os.getenv("NEO4J_URL", "bolt://localhost:7687"),
            args.username or os.getenv("NEO4J_USERNAME", "neo4j"),
            args.password or os.getenv("NEO4J_PASSWORD", "password"),
        )
    )

__all__ = ["main", "server"]
