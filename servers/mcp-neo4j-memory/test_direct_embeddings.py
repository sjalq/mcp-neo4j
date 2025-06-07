#!/usr/bin/env python3
"""Test script to verify VectorEnabledNeo4jMemory embeddings work"""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mcp_neo4j_memory.vector_memory import VectorEnabledNeo4jMemory
from mcp_neo4j_memory.server import Entity
from neo4j import GraphDatabase

async def test_embeddings():
    """Test creating entities with embeddings"""
    print("🧪 Testing VectorEnabledNeo4jMemory direct embeddings...")
    
    # Connect to Neo4j
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password123'))
    
    try:
        # Create memory instance (no auto-migrate to avoid migration logs)
        memory = VectorEnabledNeo4jMemory(driver, auto_migrate=False)
        print("✅ VectorEnabledNeo4jMemory initialized")
        
        # Create test entity
        test_entity = Entity(
            name='Direct Embedding Test Entity',
            type='DirectEmbeddingTest', 
            observations=['This should have BGE-large embeddings', 'Testing direct creation']
        )
        
        print(f"🔄 Creating entity: {test_entity.name}")
        result = await memory.create_entities([test_entity])
        print(f"✅ Created: {result[0].name}")
        
        # Check if it has embeddings
        check_query = """
        MATCH (m:Memory {name: $name})
        RETURN m.content_embedding IS NOT NULL as has_embedding,
               size(m.content_embedding) as embedding_size
        """
        
        check_result = driver.execute_query(check_query, {"name": test_entity.name})
        
        if check_result.records:
            record = check_result.records[0]
            has_embedding = record["has_embedding"]
            embedding_size = record["embedding_size"]
            
            if has_embedding:
                print(f"🎉 SUCCESS! Entity has embedding with {embedding_size} dimensions")
            else:
                print("❌ FAILED! Entity has no embedding")
        else:
            print("❌ FAILED! Entity not found")
            
    finally:
        driver.close()

if __name__ == "__main__":
    asyncio.run(test_embeddings()) 