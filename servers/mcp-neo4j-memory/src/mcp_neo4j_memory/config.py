# Configuration for BGE-large vector embeddings

# Model settings
EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIMENSIONS = 1024  # BGE-large uses 1024 dimensions
SIMILARITY_THRESHOLD = 0.7   # Higher threshold for 1024-dim space
BATCH_SIZE = 16              # Optimal batch size for BGE-large on CPU

# Vector index settings - single unified index
VECTOR_INDEXES = [
    {
        "name": "entity_embeddings",
        "label": "Entity",
        "property": "embedding"
    }
]

# Note: SEARCH_MODES removed - now using unified single embedding approach 