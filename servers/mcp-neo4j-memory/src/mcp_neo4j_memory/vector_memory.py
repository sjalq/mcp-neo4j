import logging
from typing import List, Dict, Any
import asyncio

from sentence_transformers import SentenceTransformer
import numpy as np
import neo4j

from .config import (
    EMBEDDING_MODEL, 
    EMBEDDING_DIMENSIONS, 
    SIMILARITY_THRESHOLD, 
    BATCH_SIZE,
    VECTOR_INDEXES,
    SEARCH_MODES
)

logger = logging.getLogger(__name__)

class VectorEnabledNeo4jMemory:
    def __init__(self, neo4j_driver, auto_migrate=True):
        self.neo4j_driver = neo4j_driver
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        self.encoder = SentenceTransformer(EMBEDDING_MODEL)
        self.encoder.max_seq_length = 512  # Optimize for memory content
        
        self.create_fulltext_index()
        self._ensure_vector_indexes()
        
        # Schedule migration check if event loop is running
        if auto_migrate:
            try:
                asyncio.create_task(self.ensure_all_indexed())
            except RuntimeError:
                # No event loop running, migration will be called manually
                logger.info("No event loop running, migration check will be called manually")

    def create_fulltext_index(self):
        """Create fulltext index for fallback search"""
        try:
            query = """
            CREATE FULLTEXT INDEX search IF NOT EXISTS 
            FOR (m:Memory) ON EACH [m.name, m.type, m.observations];
            """
            self.neo4j_driver.execute_query(query)
            logger.info("Created fulltext search index")
        except neo4j.exceptions.ClientError as e:
            if "An index with this name already exists" in str(e):
                logger.info("Fulltext search index already exists")
            else:
                raise e

    def _ensure_vector_indexes(self):
        """Create all necessary vector indexes"""
        for index_config in VECTOR_INDEXES:
            self._create_vector_index(**index_config)

    def _create_vector_index(self, name: str, label: str, property: str):
        """Create a single vector index"""
        try:
            query = f"""
            CREATE VECTOR INDEX {name} IF NOT EXISTS
            FOR (m:{label}) 
            ON m.{property}
            OPTIONS {{
                indexConfig: {{
                    `vector.dimensions`: {EMBEDDING_DIMENSIONS},
                    `vector.similarity_function`: 'cosine'
                }}
            }}
            """
            self.neo4j_driver.execute_query(query)
            logger.info(f"Created vector index: {name}")
        except neo4j.exceptions.ClientError as e:
            if "already exists" in str(e):
                logger.info(f"Vector index {name} already exists")
            else:
                logger.error(f"Failed to create vector index {name}: {e}")
                raise e

    def _generate_embeddings(self, entity) -> Dict[str, List[float]]:
        """Generate multiple embeddings for different search contexts"""
        
        # 1. Full content embedding (name + type + all observations)
        full_content = f"{entity.name} is a {entity.type}. {' '.join(entity.observations)}"
        content_embedding = self.encoder.encode(full_content).tolist()
        
        # 2. Observation-only embedding (for semantic observation search)
        observation_content = ' '.join(entity.observations) if entity.observations else entity.name
        observation_embedding = self.encoder.encode(observation_content).tolist()
        
        # 3. Entity identity embedding (name + type only)
        identity_content = f"{entity.name} ({entity.type})"
        identity_embedding = self.encoder.encode(identity_content).tolist()
        
        return {
            "content_embedding": content_embedding,
            "observation_embedding": observation_embedding, 
            "identity_embedding": identity_embedding
        }

    async def create_entities(self, entities: List) -> List:
        """Enhanced entity creation with automatic embedding generation"""
        
        if not entities:
            return entities
            
        # Generate embeddings in batches for efficiency
        batch_embeddings = []
        for i in range(0, len(entities), BATCH_SIZE):
            batch = entities[i:i+BATCH_SIZE]
            embeddings = [self._generate_embeddings(entity) for entity in batch]
            batch_embeddings.extend(embeddings)
            logger.info(f"Generated embeddings for batch {i//BATCH_SIZE + 1}")

        # Enhanced Cypher query with multiple embeddings
        query = """
        UNWIND $entities as entity
        MERGE (e:Memory { name: entity.name })
        SET e += entity {
            .type, 
            .observations,
            .content_embedding,
            .observation_embedding,
            .identity_embedding
        }
        SET e:$(entity.type)
        SET e.indexed_at = datetime()
        """
        
        # Prepare data with embeddings
        entities_data = []
        for entity, embeddings in zip(entities, batch_embeddings):
            data = entity.model_dump() if hasattr(entity, 'model_dump') else entity.__dict__
            data.update(embeddings)
            entities_data.append(data)
        
        self.neo4j_driver.execute_query(query, {"entities": entities_data})
        logger.info(f"Created {len(entities)} entities with embeddings")
        return entities

    async def create_relations(self, relations: List) -> List:
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
        
        logger.info(f"Created {len(relations)} relations with embeddings")
        return relations

    async def vector_search(
        self, 
        query: str, 
        mode: str = "content",
        limit: int = 10,
        threshold: float = SIMILARITY_THRESHOLD
    ):
        """Advanced vector search with multiple modes"""
        
        query_embedding = self.encoder.encode(query).tolist()
        
        # Choose embedding field based on search mode
        embedding_property = SEARCH_MODES.get(mode, "content_embedding")
        index_name = f"memory_{mode}_embeddings"
        
        vector_query = f"""
        CALL db.index.vector.queryNodes(
            '{index_name}', 
            $limit, 
            $embedding
        )
        YIELD node, score
        WHERE score >= $threshold
        WITH node, score
        ORDER BY score DESC
        
        // Get related entities within 1 hop
        OPTIONAL MATCH (node)-[r]-(related:Memory)
        WHERE id(related) <> id(node)
        
        WITH node, score, 
             collect(DISTINCT related)[0..5] as related_nodes,
             collect(DISTINCT r)[0..10] as related_rels
        
        RETURN collect({{
            name: node.name,
            type: node.type, 
            observations: node.observations,
            score: score
        }}) as nodes,
        collect(DISTINCT {{
            source: startNode(related_rels[0]).name,
            target: endNode(related_rels[0]).name, 
            relationType: type(related_rels[0])
        }}) as relations
        """
        
        result = self.neo4j_driver.execute_query(vector_query, {
            "embedding": query_embedding,
            "limit": limit * 2,  # Get more for filtering
            "threshold": threshold
        })
        
        return self._process_vector_results(result)

    def _process_vector_results(self, result):
        """Process Neo4j vector search results into KnowledgeGraph format"""
        from .server import Entity, Relation, KnowledgeGraph
        
        if not result.records:
            return KnowledgeGraph(entities=[], relations=[])
        
        record = result.records[0]
        nodes_data = record.get('nodes', [])
        relations_data = record.get('relations', [])
        
        entities = [
            Entity(
                name=node.get('name', ''),
                type=node.get('type', ''),
                observations=node.get('observations', [])
            )
            for node in nodes_data if node.get('name')
        ]
        
        relations = [
            Relation(
                source=rel.get('source', ''),
                target=rel.get('target', ''),
                relationType=rel.get('relationType', '')
            )
            for rel in relations_data 
            if rel.get('source') and rel.get('target') and rel.get('relationType')
        ]
        
        return KnowledgeGraph(entities=entities, relations=relations)

    async def smart_search(self, query: str, limit: int = 10):
        """Intelligent search routing based on query characteristics"""
        
        query_lower = query.lower()
        words = query.split()
        
        # Short, specific queries → try exact match first
        if len(words) <= 2 and not any(q in query_lower for q in ['what', 'how', 'why']):
            exact_result = await self.find_nodes(words)
            if exact_result.entities:
                return exact_result
        
        # Question-based queries → content search
        if any(q in query_lower for q in ['what is', 'who is', 'tell me about', 'explain']):
            return await self.vector_search(query, mode="content", limit=limit)
        
        # Behavioral/observational queries → observation search  
        if any(q in query_lower for q in ['does', 'can', 'did', 'involved in', 'related to']):
            return await self.vector_search(query, mode="observations", limit=limit)
        
        # Default: hybrid content search
        return await self.vector_search(query, mode="content", limit=limit)

    # Migration methods
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
            from .server import Entity
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

    async def _update_embeddings_batch(self, entities: List):
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

    # Fallback methods to maintain compatibility
    async def load_graph(self, filter_query="*"):
        """Fallback to fulltext search"""
        query = """
            CALL db.index.fulltext.queryNodes('search', $filter) yield node as entity, score
            OPTIONAL MATCH (entity)-[r]-(other)
            RETURN collect(distinct {
                name: entity.name, 
                type: entity.type, 
                observations: entity.observations
            }) as nodes,
            collect(distinct {
                source: startNode(r).name, 
                target: endNode(r).name, 
                relationType: type(r)
            }) as relations
        """
        
        result = self.neo4j_driver.execute_query(query, {"filter": filter_query})
        return self._process_fulltext_results(result)

    def _process_fulltext_results(self, result):
        """Process fulltext search results"""
        from .server import Entity, Relation, KnowledgeGraph
        
        if not result.records:
            return KnowledgeGraph(entities=[], relations=[])
        
        record = result.records[0]
        nodes = record.get('nodes')
        rels = record.get('relations')
        
        entities = [
            Entity(
                name=node.get('name'),
                type=node.get('type'),
                observations=node.get('observations', [])
            )
            for node in nodes if node.get('name')
        ]
        
        relations = [
            Relation(
                source=rel.get('source'),
                target=rel.get('target'),
                relationType=rel.get('relationType')
            )
            for rel in rels if rel.get('source') and rel.get('target') and rel.get('relationType')
        ]
        
        return KnowledgeGraph(entities=entities, relations=relations)

    async def search_nodes(self, query: str):
        """Enhanced search that tries vector first, fallback to fulltext"""
        try:
            # Try smart vector search first
            result = await self.smart_search(query)
            if result.entities:
                return result
        except Exception as e:
            logger.warning(f"Vector search failed, falling back to fulltext: {e}")
        
        # Fallback to fulltext
        return await self.load_graph(query)

    async def find_nodes(self, names: List[str]):
        """Find specific nodes by name"""
        return await self.load_graph("name: (" + " ".join(names) + ")")

    async def read_graph(self):
        """Read entire graph"""
        return await self.load_graph()

    # Delegation methods for other operations
    async def add_observations(self, observations: List):
        """Add observations and update embeddings"""
        # First add the observations using standard method
        query = """
        UNWIND $observations as obs  
        MATCH (e:Memory { name: obs.entityName })
        WITH e, [o in obs.contents WHERE NOT o IN e.observations] as new
        SET e.observations = coalesce(e.observations,[]) + new
        RETURN e.name as name, new
        """
            
        result = self.neo4j_driver.execute_query(
            query, 
            {"observations": [obs.model_dump() if hasattr(obs, 'model_dump') else obs.__dict__ for obs in observations]}
        )

        # Then update embeddings for affected entities
        for obs in observations:
            entity_query = """
            MATCH (e:Memory { name: $name })
            RETURN e.name as name, e.type as type, e.observations as observations
            """
            entity_result = self.neo4j_driver.execute_query(entity_query, {"name": obs.entityName})
            
            if entity_result.records:
                from .server import Entity
                record = entity_result.records[0]
                entity = Entity(
                    name=record["name"],
                    type=record["type"],
                    observations=record["observations"] or []
                )
                
                # Regenerate embeddings
                embeddings = self._generate_embeddings(entity)
                
                update_query = """
                MATCH (e:Memory { name: $name })
                SET e.content_embedding = $content_embedding
                SET e.observation_embedding = $observation_embedding
                SET e.identity_embedding = $identity_embedding
                SET e.indexed_at = datetime()
                """
                
                self.neo4j_driver.execute_query(update_query, {
                    "name": entity.name,
                    **embeddings
                })

        results = [{"entityName": record.get("name"), "addedObservations": record.get("new")} for record in result.records]
        return results

    async def delete_entities(self, entity_names: List[str]) -> None:
        """Delete entities and their embeddings"""
        query = """
        UNWIND $entities as name
        MATCH (e:Memory { name: name })
        DETACH DELETE e
        """
        
        self.neo4j_driver.execute_query(query, {"entities": entity_names})

    async def delete_observations(self, deletions: List) -> None:
        """Delete observations and update embeddings"""
        query = """
        UNWIND $deletions as d  
        MATCH (e:Memory { name: d.entityName })
        SET e.observations = [o in coalesce(e.observations,[]) WHERE NOT o IN d.observations]
        """
        self.neo4j_driver.execute_query(
            query, 
            {
                "deletions": [deletion.model_dump() if hasattr(deletion, 'model_dump') else deletion.__dict__ for deletion in deletions]
            }
        )
        
        # Update embeddings for affected entities
        for deletion in deletions:
            entity_query = """
            MATCH (e:Memory { name: $name })
            RETURN e.name as name, e.type as type, e.observations as observations
            """
            entity_result = self.neo4j_driver.execute_query(entity_query, {"name": deletion.entityName})
            
            if entity_result.records:
                from .server import Entity
                record = entity_result.records[0]
                entity = Entity(
                    name=record["name"],
                    type=record["type"],
                    observations=record["observations"] or []
                )
                
                # Regenerate embeddings
                embeddings = self._generate_embeddings(entity)
                
                update_query = """
                MATCH (e:Memory { name: $name })
                SET e.content_embedding = $content_embedding
                SET e.observation_embedding = $observation_embedding
                SET e.identity_embedding = $identity_embedding
                SET e.indexed_at = datetime()
                """
                
                self.neo4j_driver.execute_query(update_query, {
                    "name": entity.name,
                    **embeddings
                })

    async def delete_relations(self, relations: List) -> None:
        """Delete relations"""
        query = """
        UNWIND $relations as relation
        MATCH (source:Memory)-[r:$(relation.relationType)]->(target:Memory)
        WHERE source.name = relation.source
        AND target.name = relation.target
        DELETE r
        """
        self.neo4j_driver.execute_query(
            query, 
            {"relations": [relation.model_dump() if hasattr(relation, 'model_dump') else relation.__dict__ for relation in relations]}
        ) 