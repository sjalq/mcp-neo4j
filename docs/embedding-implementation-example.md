# Example modifications for embedding support in mcp-neo4j-memory

## 1. Modified Entity Creation with Embeddings

```python
from sentence_transformers import SentenceTransformer
import numpy as np

class Neo4jMemory:
    def __init__(self, neo4j_driver):
        self.neo4j_driver = neo4j_driver
        self.encoder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        self.create_fulltext_index()
        self.create_vector_index()
    
    def create_vector_index(self):
        """Create vector index for semantic search"""
        query = """
        CREATE VECTOR INDEX memory_embeddings IF NOT EXISTS
        FOR (m:Memory) 
        ON m.embedding
        OPTIONS {
            indexConfig: {
                `vector.dimensions`: 384,
                `vector.similarity_function`: 'cosine'
            }
        }
        """
        self.neo4j_driver.execute_query(query)
    
    async def create_entities(self, entities: List[Entity]) -> List[Entity]:
        """Modified to include embedding generation"""
        query = """
        UNWIND $entities as entity
        MERGE (e:Memory { name: entity.name })
        SET e += entity {.type, .observations, .embedding}
        SET e:$(entity.type)
        """
        
        # Prepare entities with embeddings
        entities_with_embeddings = []
        for entity in entities:
            # Combine all text for rich embedding
            text = f"{entity.name} is a {entity.type}. {' '.join(entity.observations)}"
            
            # Generate embedding (384 dimensions)
            embedding = self.encoder.encode(text).tolist()
            
            entity_data = entity.model_dump()
            entity_data['embedding'] = embedding
            entities_with_embeddings.append(entity_data)
        
        self.neo4j_driver.execute_query(query, {"entities": entities_with_embeddings})
        return entities
```

## 2. Hybrid Retrieval (Vector + Fulltext)

```python
async def search_nodes(self, query: str, mode: str = "hybrid") -> KnowledgeGraph:
    """Enhanced search with vector similarity"""
    
    if mode == "vector" or mode == "hybrid":
        # Generate query embedding
        query_embedding = self.encoder.encode(query).tolist()
        
        # Vector search
        vector_query = """
        CALL db.index.vector.queryNodes('memory_embeddings', 20, $embedding)
        YIELD node, score
        WHERE score > 0.5  // Similarity threshold
        WITH node, score
        ORDER BY score DESC
        LIMIT 10
        OPTIONAL MATCH (node)-[r]-(other:Memory)
        RETURN collect(distinct {
            name: node.name, 
            type: node.type, 
            observations: node.observations,
            score: score
        }) as nodes,
        collect(distinct {
            source: startNode(r).name, 
            target: endNode(r).name, 
            relationType: type(r)
        }) as relations
        """
        
        result = self.neo4j_driver.execute_query(
            vector_query, 
            {"embedding": query_embedding}
        )
    
    if mode == "fulltext" or (mode == "hybrid" and not result.records):
        # Fallback to fulltext
        return await self.load_graph(query)
    
    # Process results...
```

## 3. Smart Query Understanding

```python
async def smart_search(self, query: str) -> KnowledgeGraph:
    """Intelligently choose search strategy based on query"""
    
    # Short queries = likely entity lookup
    if len(query.split()) <= 3:
        # Try exact match first
        exact_result = await self.find_nodes([query])
        if exact_result.entities:
            return exact_result
    
    # Questions or complex queries = semantic search
    if any(word in query.lower() for word in ['what', 'who', 'why', 'how', 'tell me about']):
        return await self.search_nodes(query, mode="vector")
    
    # Default to hybrid
    return await self.search_nodes(query, mode="hybrid")
```

## 4. Update Existing Entities with Embeddings

```python
async def add_observations(self, observations: List[ObservationAddition]):
    """Modified to update embeddings when observations change"""
    # First, add observations as before
    result = await super().add_observations(observations)
    
    # Then update embeddings for affected entities
    update_query = """
    UNWIND $updates as update
    MATCH (e:Memory { name: update.name })
    SET e.embedding = update.embedding
    """
    
    updates = []
    for obs in observations:
        # Get current entity data
        entity = await self.find_nodes([obs.entityName])
        if entity.entities:
            e = entity.entities[0]
            # Regenerate embedding with new observations
            text = f"{e.name} is a {e.type}. {' '.join(e.observations)}"
            embedding = self.encoder.encode(text).tolist()
            updates.append({"name": e.name, "embedding": embedding})
    
    if updates:
        self.neo4j_driver.execute_query(update_query, {"updates": updates})
    
    return result
```

## 5. Usage Examples

```python
# Creating entities with automatic embeddings
entities = [
    Entity(
        name="Cyril Ramaphosa",
        type="Person",
        observations=[
            "President of South Africa",
            "Involved in Phala Phala scandal",
            "Stashed cash in his couch"
        ]
    )
]
await memory.create_entities(entities)

# Semantic search
results = await memory.smart_search("politicians involved in scandals")
# Will find Cyril even though "politician" and "scandal" aren't exact matches

# Find similar entities
results = await memory.search_nodes("corruption controversies", mode="vector")
```

## Key Points:

1. **Embedding Generation**: Combine name + type + observations for richer context
2. **Storage**: 384-dimensional float array stored on each Memory node
3. **Retrieval**: Use Neo4j's vector index with cosine similarity
4. **Hybrid Search**: Try vector first, fallback to fulltext
5. **Threshold**: Use similarity > 0.5 to filter noise
6. **Updates**: Regenerate embeddings when observations change

The beauty is that your existing API doesn't change - embeddings happen transparently! 