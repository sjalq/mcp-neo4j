# Configuration for BGE-large vector embeddings

# Model settings
EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIMENSIONS = 1024  # BGE-large uses 1024 dimensions
SIMILARITY_THRESHOLD = 0.7   # Higher threshold for 1024-dim space
BATCH_SIZE = 16              # Optimal batch size for BGE-large on CPU

# Vector index settings
VECTOR_INDEXES = [
    {
        "name": "memory_content_embeddings",
        "label": "Memory",
        "property": "content_embedding"
    },
    {
        "name": "memory_observation_embeddings", 
        "label": "Memory",
        "property": "observation_embedding"
    },
    {
        "name": "memory_identity_embeddings",
        "label": "Memory", 
        "property": "identity_embedding"
    }
]

# Search modes
SEARCH_MODES = {
    "content": "content_embedding",      # Full context search
    "observations": "observation_embedding",  # Observation-specific
    "identity": "identity_embedding",   # Entity name/type focused
} 