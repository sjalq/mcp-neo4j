# Configuration for BGE-large vector embeddings

# Model settings
EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIMENSIONS = 1024  # BGE-large uses 1024 dimensions
SIMILARITY_THRESHOLD = 0.7   # Higher threshold for 1024-dim space
BATCH_SIZE = 16              # Optimal batch size for BGE-large on CPU

# Vector index settings - use existing memory_embeddings_v2 index
VECTOR_INDEXES = [
    {
        "name": "memory_embeddings_v2",
        "label": "Memory",  # Universal label for all memory nodes
        "property": "embedding"
    }
]

# Note: Universal embedding approach - all memory nodes get Memory label for indexing 