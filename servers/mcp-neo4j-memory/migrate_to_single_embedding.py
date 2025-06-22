#!/usr/bin/env python3
"""
Migration Script: Single Embedding Migration
Migrates from multi-embedding (content, observation, identity) to single unified embedding.

This script:
1. Drops old vector indexes 
2. Creates new single vector index
3. Finds entities with old embeddings but no new embedding
4. Generates new unified embeddings for all entities
5. Removes old embedding properties

Usage:
    python migrate_to_single_embedding.py --neo4j-uri bolt://localhost:7687 --username neo4j --password password
"""

import asyncio
import argparse
import logging
import os
from typing import List, Dict
import neo4j
from sentence_transformers import SentenceTransformer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SingleEmbeddingMigrator:
    def __init__(self, neo4j_uri: str, username: str, password: str):
        self.driver = neo4j.GraphDatabase.driver(neo4j_uri, auth=(username, password))
        self.encoder = SentenceTransformer("BAAI/bge-large-en-v1.5")
        logger.info("Initialized migrator with BGE-large model")

    def close(self):
        self.driver.close()

    def drop_old_indexes(self):
        """Drop the old multi-embedding vector indexes"""
        old_indexes = [
            "entity_content_embeddings",
            "entity_observation_embeddings", 
            "entity_identity_embeddings"
        ]
        
        for index_name in old_indexes:
            try:
                query = f"DROP INDEX {index_name} IF EXISTS"
                self.driver.execute_query(query)
                logger.info(f"Dropped old index: {index_name}")
            except Exception as e:
                logger.warning(f"Could not drop index {index_name}: {e}")

    def create_new_index(self):
        """Create the new single unified vector index"""
        try:
            query = """
            CREATE VECTOR INDEX entity_embeddings IF NOT EXISTS
            FOR (m:Entity) 
            ON m.embedding
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 1024,
                    `vector.similarity_function`: 'cosine'
                }
            }
            """
            self.driver.execute_query(query)
            logger.info("Created new unified vector index: entity_embeddings")
        except Exception as e:
            logger.error(f"Failed to create new index: {e}")
            raise

    def find_entities_to_migrate(self) -> List[Dict]:
        """Find entities that need migration to single embedding"""
        query = """
        MATCH (m:Entity)
        WHERE m.embedding IS NULL 
        AND (m.content_embedding IS NOT NULL OR m.observation_embedding IS NOT NULL OR m.identity_embedding IS NOT NULL)
        RETURN m.name as name, m.type as type, coalesce(m.observations, []) as observations
        ORDER BY m.name
        """
        
        result = self.driver.execute_query(query)
        entities = []
        
        for record in result.records:
            entities.append({
                "name": record["name"],
                "type": record["type"], 
                "observations": record["observations"]
            })
        
        logger.info(f"Found {len(entities)} entities to migrate")
        return entities

    def generate_single_embedding(self, entity: Dict) -> List[float]:
        """Generate single unified embedding for an entity"""
        # Combine all entity context into one comprehensive text
        full_context = f"{entity['name']} is a {entity['type']}. {' '.join(entity['observations'])}"
        embedding = self.encoder.encode(full_context).tolist()
        return embedding

    def migrate_entities_batch(self, entities: List[Dict], batch_size: int = 16):
        """Migrate entities in batches to avoid memory issues"""
        for i in range(0, len(entities), batch_size):
            batch = entities[i:i+batch_size]
            
            # Generate embeddings for batch
            updates = []
            for entity in batch:
                embedding = self.generate_single_embedding(entity)
                updates.append({
                    "name": entity["name"],
                    "embedding": embedding
                })
            
            # Update database in batch
            query = """
            UNWIND $updates as update
            MATCH (m:Entity {name: update.name})
            SET m.embedding = update.embedding
            SET m.indexed_at = datetime()
            """
            
            self.driver.execute_query(query, {"updates": updates})
            logger.info(f"Migrated batch {i//batch_size + 1}/{(len(entities)-1)//batch_size + 1}")

    def cleanup_old_properties(self):
        """Remove old embedding properties after successful migration"""
        query = """
        MATCH (m:Entity)
        WHERE m.embedding IS NOT NULL
        REMOVE m.content_embedding, m.observation_embedding, m.identity_embedding
        RETURN count(m) as cleaned_count
        """
        
        result = self.driver.execute_query(query)
        count = result.records[0]["cleaned_count"] if result.records else 0
        logger.info(f"Cleaned up old embedding properties from {count} entities")

    def verify_migration(self):
        """Verify migration was successful"""
        queries = {
            "entities_with_new_embedding": "MATCH (m:Entity) WHERE m.embedding IS NOT NULL RETURN count(m) as count",
            "entities_with_old_embeddings": "MATCH (m:Entity) WHERE m.content_embedding IS NOT NULL OR m.observation_embedding IS NOT NULL OR m.identity_embedding IS NOT NULL RETURN count(m) as count",
            "total_entities": "MATCH (m:Entity) RETURN count(m) as count"
        }
        
        results = {}
        for name, query in queries.items():
            result = self.driver.execute_query(query)
            results[name] = result.records[0]["count"] if result.records else 0
        
        logger.info("Migration verification:")
        logger.info(f"  Total entities: {results['total_entities']}")
        logger.info(f"  Entities with new embedding: {results['entities_with_new_embedding']}")
        logger.info(f"  Entities with old embeddings: {results['entities_with_old_embeddings']}")
        
        if results['entities_with_new_embedding'] == results['total_entities'] and results['entities_with_old_embeddings'] == 0:
            logger.info("✅ Migration completed successfully!")
            return True
        else:
            logger.warning("⚠️ Migration may not be complete")
            return False

    async def run_migration(self, cleanup: bool = False):
        """Run the complete migration process"""
        try:
            logger.info("Starting single embedding migration...")
            
            # Step 1: Drop old indexes
            logger.info("Step 1: Dropping old vector indexes...")
            self.drop_old_indexes()
            
            # Step 2: Create new index
            logger.info("Step 2: Creating new unified vector index...")
            self.create_new_index()
            
            # Step 3: Find entities to migrate
            logger.info("Step 3: Finding entities to migrate...")
            entities = self.find_entities_to_migrate()
            
            if not entities:
                logger.info("No entities need migration")
                return
            
            # Step 4: Migrate entities
            logger.info(f"Step 4: Migrating {len(entities)} entities...")
            self.migrate_entities_batch(entities)
            
            # Step 5: Cleanup old properties (optional)
            if cleanup:
                logger.info("Step 5: Cleaning up old embedding properties...")
                self.cleanup_old_properties()
            else:
                logger.info("Step 5: Skipping cleanup (use --cleanup to remove old properties)")
            
            # Step 6: Verify migration
            logger.info("Step 6: Verifying migration...")
            success = self.verify_migration()
            
            if success:
                logger.info("🎉 Migration completed successfully!")
            else:
                logger.error("❌ Migration verification failed")
                
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise

def main():
    parser = argparse.ArgumentParser(description="Migrate Neo4j memory to single embedding approach")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687", help="Neo4j URI")
    parser.add_argument("--username", default="neo4j", help="Neo4j username")
    parser.add_argument("--password", required=True, help="Neo4j password")
    parser.add_argument("--cleanup", action="store_true", help="Remove old embedding properties after migration")
    
    args = parser.parse_args()
    
    # Check for password in environment if not provided
    if not args.password:
        args.password = os.getenv("NEO4J_PASSWORD")
        if not args.password:
            logger.error("Password required via --password or NEO4J_PASSWORD environment variable")
            return 1
    
    migrator = SingleEmbeddingMigrator(args.neo4j_uri, args.username, args.password)
    
    try:
        asyncio.run(migrator.run_migration(cleanup=args.cleanup))
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return 1
    finally:
        migrator.close()
    
    return 0

if __name__ == "__main__":
    exit(main()) 