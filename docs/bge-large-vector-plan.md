# BGE-Large Vector Implementation Plan for MCP Neo4j Memory

## Executive Summary

Comprehensive plan to add BAAI/bge-large-en-v1.5 vector embeddings to the Neo4j MCP memory system with automatic indexing, migration tools, and robust testing.

## Phase 1: Dependencies & Setup

### 1.1 Update Dependencies
```toml
# pyproject.toml additions
dependencies = [
    "mcp>=0.10.0",
    "neo4j>=5.26.0",
    "sentence-transformers>=2.7.0",
    "torch>=2.0.0",
    "numpy>=1.24.0",
]

dev-dependencies = [
    "pytest>=8.3.5",
    "pytest-asyncio>=0.25.3",
    "pytest-mock>=3.12.0",
    "pytest-benchmark>=4.0.0",
]
```

### 1.2 Model Configuration
```python
# src/mcp_neo4j_memory/config.py
EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIMENSIONS = 1024  # BGE-large uses 1024 dims
SIMILARITY_THRESHOLD = 0.7   # Higher threshold for 1024-dim space
BATCH_SIZE = 16              # Optimal for BGE-large
```

## Phase 2: Core Vector Infrastructure

### 2.1 Enhanced Neo4j Memory Class
```python
# src/mcp_neo4j_memory/vector_memory.py
from sentence_transformers import SentenceTransformer
import numpy as np

class VectorEnabledNeo4jMemory(Neo4jMemory):
    def __init__(self, neo4j_driver):
        super().__init__(neo4j_driver)
        self.encoder = SentenceTransformer(EMBEDDING_MODEL)
        self.encoder.max_seq_length = 512  # Optimize for memory content
        self._ensure_vector_indexes()
    
    def _ensure_vector_indexes(self):
        """Create all necessary vector indexes"""
        indexes = [
            # Primary memory embeddings
            {
                "name": "memory_content_embeddings",
                "label": "Memory",
                "property": "content_embedding"
            },
            # Observation-specific embeddings
            {
                "name": "memory_observation_embeddings", 
                "label": "Memory",
                "property": "observation_embedding"
            },
            # Relationship embeddings
            {
                "name": "relationship_embeddings",
                "relationship": True,
                "property": "context_embedding"
            }
        ]
        
        for index in indexes:
            self._create_vector_index(**index)
```

### 2.2 Multi-Level Embedding Strategy
```python
def _generate_embeddings(self, entity: Entity) -> dict:
    """Generate multiple embeddings for different search contexts"""
    
    # 1. Full content embedding (name + type + all observations)
    full_content = f"{entity.name} is a {entity.type}. {' '.join(entity.observations)}"
    content_embedding = self.encoder.encode(full_content).tolist()
    
    # 2. Observation-only embedding (for semantic observation search)
    observation_content = ' '.join(entity.observations)
    observation_embedding = self.encoder.encode(observation_content).tolist()
    
    # 3. Entity identity embedding (name + type only)
    identity_content = f"{entity.name} ({entity.type})"
    identity_embedding = self.encoder.encode(identity_content).tolist()
    
    return {
        "content_embedding": content_embedding,
        "observation_embedding": observation_embedding, 
        "identity_embedding": identity_embedding
    }
```

## Phase 3: Automatic Indexing System

### 3.1 Create with Embeddings
```python
async def create_entities(self, entities: List[Entity]) -> List[Entity]:
    """Enhanced entity creation with automatic embedding generation"""
    
    # Generate embeddings in batches for efficiency
    batch_embeddings = []
    for i in range(0, len(entities), BATCH_SIZE):
        batch = entities[i:i+BATCH_SIZE]
        embeddings = [self._generate_embeddings(entity) for entity in batch]
        batch_embeddings.extend(embeddings)
    
    # Enhanced Cypher query with multiple embeddings
    query = """
    UNWIND $entities as entity
    MERGE (e:Memory { name: entity.name })
    SET e += entity {
        .type, 
        .observations,
        .content_embedding,
        .observation_embedding,
        .identity_embedding,
        .indexed_at
    }
    SET e:$(entity.type)
    SET e.indexed_at = datetime()
    """
    
    # Prepare data with embeddings
    entities_data = []
    for entity, embeddings in zip(entities, batch_embeddings):
        data = entity.model_dump()
        data.update(embeddings)
        entities_data.append(data)
    
    self.neo4j_driver.execute_query(query, {"entities": entities_data})
    return entities
```

### 3.2 Relationship Embedding
```python
async def create_relations(self, relations: List[Relation]) -> List[Relation]:
    """Enhanced relation creation with context embeddings"""
    
    for relation in relations:
        # Generate context embedding for relationship
        context_text = f"{relation.source} {relation.relationType} {relation.target}"
        context_embedding = self.encoder.encode(context_text).tolist()
        
        query = """
        MATCH (from:Memory {name: $source}), (to:Memory {name: $target})
        MERGE (from)-[r:$(relationType)]->(to)
        SET r.context_embedding = $context_embedding
        SET r.created_at = datetime()
        """
        
        self.neo4j_driver.execute_query(query, {
            "source": relation.source,
            "target": relation.target, 
            "relationType": relation.relationType,
            "context_embedding": context_embedding
        })
    
    return relations
```

## Phase 4: Migration & Indexing Unindexed Items

### 4.1 Migration Script
```python
# src/mcp_neo4j_memory/migrate.py
async def migrate_existing_memories(self):
    """Add embeddings to existing memories that lack them"""
    
    # Find unindexed memories
    query = """
    MATCH (m:Memory)
    WHERE m.content_embedding IS NULL
    RETURN m.name as name, m.type as type, m.observations as observations
    ORDER BY m.name
    """
    
    result = self.neo4j_driver.execute_query(query)
    unindexed = []
    
    for record in result.records:
        entity = Entity(
            name=record["name"],
            type=record["type"], 
            observations=record["observations"] or []
        )
        unindexed.append(entity)
    
    if unindexed:
        logger.info(f"Migrating {len(unindexed)} unindexed memories...")
        
        # Process in batches
        for i in range(0, len(unindexed), BATCH_SIZE):
            batch = unindexed[i:i+BATCH_SIZE]
            await self._update_embeddings_batch(batch)
            logger.info(f"Migrated batch {i//BATCH_SIZE + 1}")

async def _update_embeddings_batch(self, entities: List[Entity]):
    """Update embeddings for existing entities"""
    updates = []
    
    for entity in entities:
        embeddings = self._generate_embeddings(entity)
        updates.append({
            "name": entity.name,
            **embeddings
        })
    
    query = """
    UNWIND $updates as update
    MATCH (m:Memory {name: update.name})
    SET m.content_embedding = update.content_embedding
    SET m.observation_embedding = update.observation_embedding  
    SET m.identity_embedding = update.identity_embedding
    SET m.indexed_at = datetime()
    """
    
    self.neo4j_driver.execute_query(query, {"updates": updates})
```

### 4.2 Health Check & Auto-Migration
```python
async def ensure_all_indexed(self):
    """Ensure all memories have embeddings, migrate if needed"""
    
    # Count unindexed items
    count_query = """
    MATCH (m:Memory)
    WHERE m.content_embedding IS NULL
    RETURN count(m) as unindexed_count
    """
    
    result = self.neo4j_driver.execute_query(count_query)
    unindexed_count = result.records[0]["unindexed_count"]
    
    if unindexed_count > 0:
        logger.warning(f"Found {unindexed_count} unindexed memories. Starting migration...")
        await self.migrate_existing_memories()
        logger.info("Migration completed successfully")
    else:
        logger.info("All memories are properly indexed")
```

## Phase 5: Advanced Vector Search

### 5.1 Multi-Mode Vector Search
```python
async def vector_search(
    self, 
    query: str, 
    mode: str = "content",
    limit: int = 10,
    threshold: float = SIMILARITY_THRESHOLD
) -> KnowledgeGraph:
    """Advanced vector search with multiple modes"""
    
    query_embedding = self.encoder.encode(query).tolist()
    
    # Choose embedding field based on search mode
    embedding_field = {
        "content": "content_embedding",      # Full context search
        "observations": "observation_embedding",  # Observation-specific
        "identity": "identity_embedding",   # Entity name/type focused
    }.get(mode, "content_embedding")
    
    vector_query = f"""
    CALL db.index.vector.queryNodes(
        'memory_{mode}_embeddings', 
        $limit, 
        $embedding
    )
    YIELD node, score
    WHERE score >= $threshold
    WITH node, score
    ORDER BY score DESC
    
    // Get related entities within 2 hops
    OPTIONAL MATCH (node)-[r1]-(related1:Memory)-[r2]-(related2:Memory)
    WHERE id(related2) <> id(node)
    
    WITH node, score, 
         collect(DISTINCT related1) as related_nodes,
         collect(DISTINCT r1) as related_rels
    
    RETURN {{
        primary: collect({{
            name: node.name,
            type: node.type, 
            observations: node.observations,
            score: score
        }}),
        related: related_nodes[0..5],  // Limit related nodes
        relationships: related_rels[0..10]
    }} as results
    """
    
    result = self.neo4j_driver.execute_query(vector_query, {
        "embedding": query_embedding,
        "limit": limit * 2,  # Get more for filtering
        "threshold": threshold
    })
    
    return self._process_vector_results(result)
```

## Phase 6: Comprehensive Testing

### 6.1 Unit Tests
```python
# tests/test_vector_search.py
import pytest
from unittest.mock import Mock

class TestVectorSearch:
    
    @pytest.mark.asyncio
    async def test_embedding_generation(self, vector_memory):
        """Test that embeddings are properly generated"""
        entity = Entity(
            name="Test Entity",
            type="TestType", 
            observations=["Test observation"]
        )
        
        embeddings = vector_memory._generate_embeddings(entity)
        
        assert "content_embedding" in embeddings
        assert "observation_embedding" in embeddings
        assert "identity_embedding" in embeddings
        assert len(embeddings["content_embedding"]) == 1024
```

### 6.2 Integration Tests
```python
# tests/test_integration.py
@pytest.mark.integration
class TestVectorIntegration:
    
    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self, real_memory):
        """Test complete workflow: create → index → search"""
        
        # Create test entities
        entities = [
            Entity(
                name="Cyril Ramaphosa",
                type="Person", 
                observations=["President of South Africa", "Phala Phala scandal"]
            )
        ]
        
        # Create entities with embeddings
        await real_memory.create_entities(entities)
        
        # Test semantic search
        results = await real_memory.vector_search("corruption scandals")
        
        assert len(results.entities) >= 1
        assert "Cyril Ramaphosa" in [e.name for e in results.entities]
```

## Phase 7: Implementation Checklist

### 7.1 Development Tasks
- [ ] Update `pyproject.toml` with new dependencies
- [ ] Create `vector_memory.py` with enhanced class
- [ ] Implement multi-level embedding generation
- [ ] Add vector index creation methods
- [ ] Create migration script for existing data
- [ ] Implement vector search methods
- [ ] Add smart search routing
- [ ] Create comprehensive test suite
- [ ] Add performance benchmarks
- [ ] Update documentation

### 7.2 Performance Targets
- Embedding generation: <2 seconds per entity
- Vector search: <500ms for 10 results
- Migration: <1 hour for 10K existing entities
- Memory usage: <4GB RAM for BGE-large

## Conclusion

This plan provides a complete roadmap for integrating BGE-large-en-v1.5 embeddings into the Neo4j MCP memory system with robust indexing, migration, and testing capabilities. 