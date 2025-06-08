import logging
from typing import List, Dict, Any, Optional
import asyncio
import os
import re

from sentence_transformers import SentenceTransformer
import numpy as np
import neo4j
import torch

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
        
        # Safe CUDA detection with fallback
        device = self._detect_device()
        logger.info(f"Using device: {device}")
        
        self.encoder = SentenceTransformer(EMBEDDING_MODEL, device=device)
        self.encoder.max_seq_length = 512  # Optimize for memory content
        
        self.create_fulltext_index()
        self._ensure_vector_indexes()
        
        # Schedule migration check if event loop is running
        if auto_migrate:
            try:
                # Check if there's an event loop and schedule migration
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule as a background task
                    asyncio.create_task(self.ensure_all_indexed())
                else:
                    # No running loop, will run migration on first tool call
                    self._migration_pending = True
            except RuntimeError:
                # No event loop, will run migration on first tool call
                self._migration_pending = True
                logger.info("No event loop running, migration will run on first tool call")
        else:
            self._migration_pending = False

    def _detect_device(self):
        """Detect the best available device for running the model"""
        # Check environment variable override first
        if os.environ.get('FORCE_CPU', '').lower() in ('1', 'true', 'yes'):
            logger.info("FORCE_CPU environment variable set, using CPU")
            return 'cpu'
            
        try:
            # Try to use GPU if available
            if torch.cuda.is_available():
                logger.info("CUDA available, using GPU")
                return 'cuda'
            else:
                logger.info("CUDA not available, using CPU")
                return 'cpu'
        except Exception as e:
            logger.warning(f"CUDA detection failed ({e}), falling back to CPU")
            return 'cpu'

    def create_fulltext_index(self):
        """Create fulltext index for fallback search"""
        try:
            query = """
            CREATE FULLTEXT INDEX search IF NOT EXISTS 
            FOR (m:Entity) ON EACH [m.name, m.type, m.observations]
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
        """Create a single vector index that works with any memory node"""
        try:
            # Create index for Entity label (for backward compatibility)
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
            
            # Note: Neo4j doesn't support WHERE clauses in vector index creation
            # We'll handle this by ensuring all memory nodes get Entity label for indexing
            
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

    def _sanitize_labels(self, labels: Optional[List[str]]) -> List[str]:
        """Sanitize and CamelCase labels according to Neo4j rules"""
        if not labels:
            return []
        
        if len(labels) > 3:
            raise ValueError("Maximum 3 labels allowed")
        
        sanitized = []
        for label in labels[:3]:  # Max 3 additional labels
            # Remove special characters and split on common separators
            cleaned = re.sub(r'[^a-zA-Z0-9_\s]', '', str(label))
            words = re.split(r'[\s_]+', cleaned)
            
            # CamelCase: first letter of each word capitalized, rest lowercase
            camel_cased = ''.join(word.capitalize() for word in words if word)
            
            # Ensure it starts with a letter (Neo4j requirement)
            if camel_cased and camel_cased[0].isalpha():
                sanitized.append(camel_cased)
            elif camel_cased:
                # If starts with number/underscore, prepend 'Label'
                sanitized.append(f"Label{camel_cased}")
        
        return sanitized

    async def create_entities(self, entities: List) -> List:
        """Enhanced entity creation with automatic embedding generation"""
        
        # Run pending migration if needed
        if hasattr(self, '_migration_pending') and self._migration_pending:
            logger.info("Running pending migration on first entity creation")
            await self.ensure_all_indexed()
            self._migration_pending = False
        
        if not entities:
            return entities
            
        # Generate embeddings in batches for efficiency
        batch_embeddings = []
        for i in range(0, len(entities), BATCH_SIZE):
            batch = entities[i:i+BATCH_SIZE]
            embeddings = [self._generate_embeddings(entity) for entity in batch]
            batch_embeddings.extend(embeddings)
            logger.info(f"Generated embeddings for batch {i//BATCH_SIZE + 1}")

        # Create entities individually with intelligent merging
        for entity, embeddings in zip(entities, batch_embeddings):
            # Get labels and sanitize them (optional for all entities now)
            additional_labels = self._sanitize_labels(entity.labels)
            
            # Always add Entity label for indexing, track user's intended labels
            if additional_labels:
                merge_query = """
                MERGE (e { name: $name, type: $type })
                ON CREATE SET e:Entity, e.observations = $observations, e.user_labels = $user_labels
                ON MATCH SET e.observations = e.observations + [obs in $observations WHERE NOT obs IN e.observations], e.user_labels = $user_labels
                SET e.content_embedding = $content_embedding
                SET e.observation_embedding = $observation_embedding
                SET e.identity_embedding = $identity_embedding
                SET e.indexed_at = datetime()
                """
                params = {
                    "name": entity.name,
                    "type": entity.type,
                    "observations": entity.observations,
                    "user_labels": additional_labels,
                    **embeddings
                }
            else:
                merge_query = """
                MERGE (e { name: $name, type: $type })
                ON CREATE SET e:Entity, e.observations = $observations
                ON MATCH SET e.observations = e.observations + [obs in $observations WHERE NOT obs IN e.observations]
                SET e.content_embedding = $content_embedding
                SET e.observation_embedding = $observation_embedding
                SET e.identity_embedding = $identity_embedding
                SET e.indexed_at = datetime()
                """
                params = {
                    "name": entity.name,
                    "type": entity.type,
                    "observations": entity.observations,
                    **embeddings
                }
            
            self.neo4j_driver.execute_query(merge_query, params)
            
            # Add custom labels if provided
            if additional_labels:
                for label in additional_labels:
                    label_query = f"MATCH (e {{name: $name}}) SET e:{label}"
                    self.neo4j_driver.execute_query(label_query, {"name": entity.name})
        logger.info(f"Created {len(entities)} entities with embeddings")
        return entities

    async def create_relations(self, relations: List) -> List:
        """Enhanced relation creation with context embeddings"""
        
        for relation in relations:
            # Generate context embedding for relationship
            context_text = f"{relation.source} {relation.relationType} {relation.target}"
            context_embedding = self.encoder.encode(context_text).tolist()
            
            # Sanitize relation type for Cypher (remove special chars, spaces)
            safe_rel_type = re.sub(r'[^a-zA-Z0-9_]', '_', relation.relationType)
            
            # Dynamic query with relation type (can't parameterize relationship types in Neo4j)
            # Find nodes by name regardless of labels (Entity or custom labels)
            query = f"""
            MATCH (from {{name: $source}})
            WHERE from:Entity OR (from.name IS NOT NULL AND from.type IS NOT NULL)
            WITH from LIMIT 1
            MATCH (to {{name: $target}})
            WHERE to:Entity OR (to.name IS NOT NULL AND to.type IS NOT NULL)
            WITH from, to LIMIT 1
            MERGE (from)-[r:{safe_rel_type}]->(to)
            SET r.context_embedding = $context_embedding
            SET r.created_at = datetime()
            """
            
            self.neo4j_driver.execute_query(query, {
                "source": relation.source,
                "target": relation.target,
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
        
        # Map search modes to actual index names
        index_mapping = {
            "content": "entity_content_embeddings",
            "observations": "entity_observation_embeddings",
            "identity": "entity_identity_embeddings"
        }
        index_name = index_mapping.get(mode, "entity_content_embeddings")
        
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
        
        // Get related entities within 1 hop (any memory node)
        OPTIONAL MATCH (node)-[r]-(related)
        WHERE id(related) <> id(node) 
        AND (related:Entity OR (related.name IS NOT NULL AND related.type IS NOT NULL))
        
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
        
        # Find unindexed entities
        query = """
        MATCH (m:Entity)
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
        MATCH (m:Entity {name: update.name})
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
        MATCH (m:Entity)
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

    def _process_graph_results_with_labels(self, result):
        """Process graph results with user-intended labels"""
        from .server import Entity, Relation, KnowledgeGraph
        
        if not result.records:
            return KnowledgeGraph(entities=[], relations=[])
        
        record = result.records[0]
        nodes = record.get('nodes')
        rels = record.get('relations')
        
        entities = []
        for node in nodes:
            if node.get('name'):
                user_labels = node.get('user_labels', [])
                entity = Entity(
                    name=node.get('name'),
                    type=node.get('type'),
                    observations=node.get('observations', []),
                    labels=user_labels if user_labels else None
                )
                entities.append(entity)
        
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
        # Direct query that finds nodes regardless of labels
        query = """
        MATCH (entity)
        WHERE entity.name IN $names AND (entity:Entity OR (entity.name IS NOT NULL AND entity.type IS NOT NULL))
        OPTIONAL MATCH (entity)-[r]-(other)
        WHERE other:Entity OR (other.name IS NOT NULL AND other.type IS NOT NULL)
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
        
        result = self.neo4j_driver.execute_query(query, {"names": names})
        return self._process_fulltext_results(result)

    async def read_graph(self):
        """Read entire graph - finds all memory entities regardless of label"""
        # Robust query that finds entities with :Entity label OR memory-like properties
        query = """
        MATCH (entity)
        WHERE entity:Entity OR (entity.name IS NOT NULL AND entity.type IS NOT NULL)
        OPTIONAL MATCH (entity)-[r]-(other)
        WHERE other:Entity OR (other.name IS NOT NULL AND other.type IS NOT NULL)
        RETURN collect(distinct {
            name: entity.name, 
            type: entity.type, 
            observations: coalesce(entity.observations, []),
            user_labels: coalesce(entity.user_labels, [])
        }) as nodes,
        collect(distinct {
            source: startNode(r).name, 
            target: endNode(r).name, 
            relationType: type(r)
        }) as relations
        """
        
        result = self.neo4j_driver.execute_query(query)
        return self._process_graph_results_with_labels(result)

    # Delegation methods for other operations
    async def add_observations(self, observations: List):
        """Add observations and update embeddings"""
        # First add the observations using standard method
        query = """
        UNWIND $observations as obs  
        MATCH (e { name: obs.entityName })
        WHERE e:Entity OR (e.name IS NOT NULL AND e.type IS NOT NULL)
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
            MATCH (e { name: $name })
            WHERE e:Entity OR (e.name IS NOT NULL AND e.type IS NOT NULL)
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
                MATCH (e { name: $name })
                WHERE e:Entity OR (e.name IS NOT NULL AND e.type IS NOT NULL)
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
        MATCH (e { name: name })
        WHERE e:Entity OR (e.name IS NOT NULL AND e.type IS NOT NULL)
        DETACH DELETE e
        """
        
        self.neo4j_driver.execute_query(query, {"entities": entity_names})

    async def delete_observations(self, deletions: List) -> None:
        """Delete observations and update embeddings"""
        query = """
        UNWIND $deletions as d  
        MATCH (e { name: d.entityName })
        WHERE e:Entity OR (e.name IS NOT NULL AND e.type IS NOT NULL)
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
            MATCH (e { name: $name })
            WHERE e:Entity OR (e.name IS NOT NULL AND e.type IS NOT NULL)
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
                MATCH (e { name: $name })
                WHERE e:Entity OR (e.name IS NOT NULL AND e.type IS NOT NULL)
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
        for relation in relations:
            # Sanitize relation type for Cypher (remove special chars, spaces)
            safe_rel_type = re.sub(r'[^a-zA-Z0-9_]', '_', relation.relationType)
            
            # Dynamic query with relation type (can't parameterize relationship types in Neo4j)
            query = f"""
            MATCH (source {{name: $source}})
            WHERE source:Entity OR (source.name IS NOT NULL AND source.type IS NOT NULL)
            WITH source LIMIT 1
            MATCH (target {{name: $target}})
            WHERE target:Entity OR (target.name IS NOT NULL AND target.type IS NOT NULL)
            WITH source, target LIMIT 1
            MATCH (source)-[r:{safe_rel_type}]->(target)
            DELETE r
            """
            
            self.neo4j_driver.execute_query(query, {
                "source": relation.source,
                "target": relation.target
            })

 