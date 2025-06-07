#!/usr/bin/env python3
"""
Test resource usage for BAAI/bge-large-en-v1.5
"""

import torch
import psutil
import time
from sentence_transformers import SentenceTransformer

# Check initial resources
print("=== Initial System Resources ===")
print(f"CPU: {psutil.cpu_percent()}%")
print(f"RAM: {psutil.virtual_memory().used / 1024**3:.2f} GB used")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"GPU Memory: {torch.cuda.memory_allocated() / 1024**2:.1f} MB allocated")
    print(f"GPU Memory: {torch.cuda.memory_reserved() / 1024**2:.1f} MB reserved")
print()

# Load model
print("Loading BAAI/bge-large-en-v1.5...")
start_time = time.time()
model = SentenceTransformer('BAAI/bge-large-en-v1.5')
load_time = time.time() - start_time

# Move to GPU if available
device = 'cuda' if torch.cuda.is_available() else 'cpu'
model = model.to(device)

print(f"✓ Model loaded in {load_time:.2f} seconds")
print(f"✓ Running on: {device}")

# Check model info
param_count = sum(p.numel() for p in model[0].auto_model.parameters())
print(f"✓ Parameters: {param_count / 1e6:.1f}M")
print()

# Check resources after loading
print("=== After Loading Model ===")
print(f"CPU: {psutil.cpu_percent()}%")
print(f"RAM: {psutil.virtual_memory().used / 1024**3:.2f} GB used")
if device == 'cuda':
    print(f"GPU Memory: {torch.cuda.memory_allocated() / 1024**2:.1f} MB allocated")
    print(f"GPU Memory: {torch.cuda.memory_reserved() / 1024**2:.1f} MB reserved")
print()

# Test encoding
test_texts = ["Test sentence"] * 100
print("Testing encoding speed...")
start_time = time.time()
embeddings = model.encode(test_texts, convert_to_tensor=True)
encode_time = time.time() - start_time

print(f"✓ Encoded {len(test_texts)} sentences in {encode_time:.3f} seconds")
print(f"✓ Throughput: {len(test_texts)/encode_time:.1f} sentences/second")
print(f"✓ Embedding shape: {embeddings.shape}")
print()

# Storage calculation
print("=== Storage Requirements ===")
dim = embeddings.shape[1]
bytes_per_embedding = dim * 4  # float32
print(f"Embedding dimensions: {dim}")
print(f"Bytes per embedding: {bytes_per_embedding:,}")
print(f"Storage for 1K embeddings: {bytes_per_embedding * 1000 / 1024**2:.2f} MB")
print(f"Storage for 1M embeddings: {bytes_per_embedding * 1e6 / 1024**3:.2f} GB")

# Cleanup
del model
torch.cuda.empty_cache()
print("\n✓ Model unloaded") 