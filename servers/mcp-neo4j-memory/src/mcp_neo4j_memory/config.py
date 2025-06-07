# Configuration for BGE-large vector embeddings

# Model settings
EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIMENSIONS = 1024  # BGE-large uses 1024 dimensions
SIMILARITY_THRESHOLD = 0.7   # Higher threshold for 1024-dim space
BATCH_SIZE = 16              # Optimal batch size for BGE-large on CPU

# Vector index settings - using Entity base label
VECTOR_INDEXES = [
    {
        "name": "entity_content_embeddings",
        "label": "Entity",
        "property": "content_embedding"
    },
    {
        "name": "entity_observation_embeddings", 
        "label": "Entity",
        "property": "observation_embedding"
    },
    {
        "name": "entity_identity_embeddings",
        "label": "Entity",
        "property": "identity_embedding"
    }
]

# Search modes
SEARCH_MODES = {
    "content": "content_embedding",      # Full context search
    "observations": "observation_embedding",  # Observation-specific
    "identity": "identity_embedding",   # Entity name/type focused
} 