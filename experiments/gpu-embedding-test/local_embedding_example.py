#!/usr/bin/env python3
"""
Example: Using BAAI/bge-base-en-v1.5 locally
Best open-source embedding model for local deployment
"""

from sentence_transformers import SentenceTransformer
import torch
import numpy as np

# Load the model (downloads on first run, ~420MB)
model = SentenceTransformer('BAAI/bge-base-en-v1.5')

# Optional: Use GPU if available
device = 'cuda' if torch.cuda.is_available() else 'cpu'
model = model.to(device)

# Example texts
documents = [
    "The cat sat on the mat",
    "A feline rested on the rug", 
    "Machine learning is fascinating",
    "I love pizza",
    "The weather is beautiful today"
]

queries = [
    "Where is the cat?",
    "Tell me about AI and ML",
    "What's the weather like?"
]

print("Encoding documents...")
doc_embeddings = model.encode(documents, convert_to_tensor=True)

print("\nEncoding queries...")
query_embeddings = model.encode(queries, convert_to_tensor=True)

print("\nFinding most similar documents for each query:")
for i, query in enumerate(queries):
    # Compute similarities
    similarities = torch.cosine_similarity(
        query_embeddings[i].unsqueeze(0), 
        doc_embeddings
    )
    
    # Get top match
    best_idx = similarities.argmax().item()
    best_score = similarities[best_idx].item()
    
    print(f"\nQuery: '{query}'")
    print(f"Best match: '{documents[best_idx]}' (score: {best_score:.3f})")

# Storage info
print(f"\n📊 Model Info:")
print(f"Device: {device}")
print(f"Embedding dimensions: {doc_embeddings.shape[1]}")
print(f"Memory per embedding: {doc_embeddings.shape[1] * 4} bytes (float32)") 