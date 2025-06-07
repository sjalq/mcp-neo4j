#!/usr/bin/env python3
"""
Simple GPU test for text embeddings using PyTorch
Tests GPU availability and performance for embedding generation
"""

import torch
import torch.nn as nn
import time
import numpy as np
from typing import List, Tuple


def check_gpu_availability() -> Tuple[bool, str]:
    """Check if GPU is available and return device info"""
    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        device_count = torch.cuda.device_count()
        return True, f"GPU available: {device_name} (Count: {device_count})"
    return False, "No GPU available, using CPU"


class SimpleEmbeddingModel(nn.Module):
    """Simple embedding model for testing GPU performance"""
    def __init__(self, vocab_size: int = 10000, embedding_dim: int = 768):
        super().__init__()
        self.embeddings = nn.Embedding(vocab_size, embedding_dim)
        self.linear1 = nn.Linear(embedding_dim, embedding_dim)
        self.linear2 = nn.Linear(embedding_dim, embedding_dim)
        self.activation = nn.ReLU()
        
    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        # Get embeddings
        embeds = self.embeddings(input_ids)
        # Simple transformations to simulate real model work
        x = self.linear1(embeds)
        x = self.activation(x)
        x = self.linear2(x)
        # Mean pooling
        output = x.mean(dim=1)
        return output


def generate_test_data(num_texts: int = 1000, seq_length: int = 128) -> torch.Tensor:
    """Generate random test data simulating tokenized text"""
    return torch.randint(0, 10000, (num_texts, seq_length))


def run_embedding_test(model: nn.Module, data: torch.Tensor, device: str, batch_size: int = 32) -> float:
    """Run embedding generation and return time taken"""
    model = model.to(device)
    data = data.to(device)
    
    start_time = time.time()
    
    # Process in batches
    all_embeddings = []
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        with torch.no_grad():
            embeddings = model(batch)
        all_embeddings.append(embeddings)
    
    # Force synchronization for accurate GPU timing
    if device == 'cuda':
        torch.cuda.synchronize()
    
    end_time = time.time()
    return end_time - start_time


def main():
    print("=== GPU Text Embedding Test ===\n")
    
    # Check GPU availability
    gpu_available, gpu_info = check_gpu_availability()
    print(f"Status: {gpu_info}")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if gpu_available:
        print(f"CUDA version: {torch.version.cuda}")
    print()
    
    # Create model and test data
    print("Setting up test...")
    model = SimpleEmbeddingModel()
    test_data = generate_test_data(num_texts=1000, seq_length=128)
    
    # Count parameters
    param_count = sum(p.numel() for p in model.parameters())
    print(f"Model parameters: {param_count:,}")
    print(f"Test data shape: {test_data.shape}")
    print()
    
    # Run CPU test
    print("Running CPU test...")
    cpu_time = run_embedding_test(model, test_data, 'cpu')
    print(f"CPU time: {cpu_time:.3f} seconds")
    print(f"CPU throughput: {len(test_data)/cpu_time:.1f} texts/second")
    
    # Run GPU test if available
    if gpu_available:
        print("\nRunning GPU test...")
        # Create fresh model to avoid any caching effects
        model_gpu = SimpleEmbeddingModel()
        gpu_time = run_embedding_test(model_gpu, test_data, 'cuda')
        print(f"GPU time: {gpu_time:.3f} seconds")
        print(f"GPU throughput: {len(test_data)/gpu_time:.1f} texts/second")
        
        speedup = cpu_time / gpu_time
        print(f"\nGPU Speedup: {speedup:.2f}x")
        
        # Memory usage
        print(f"\nGPU Memory allocated: {torch.cuda.memory_allocated()/1024**2:.1f} MB")
        print(f"GPU Memory reserved: {torch.cuda.memory_reserved()/1024**2:.1f} MB")
    else:
        print("\nGPU not available for comparison")
    
    # Test with real embedding computation
    print("\n=== Testing with real embedding similarity ===")
    
    # Generate a few sample embeddings
    model.eval()
    small_test = generate_test_data(num_texts=5, seq_length=64)
    
    device = 'cuda' if gpu_available else 'cpu'
    model = model.to(device)
    small_test = small_test.to(device)
    
    with torch.no_grad():
        embeddings = model(small_test)
    
    # Compute cosine similarities
    embeddings_norm = embeddings / embeddings.norm(dim=1, keepdim=True)
    similarities = torch.mm(embeddings_norm, embeddings_norm.t())
    
    print("Cosine similarity matrix (5x5):")
    print(similarities.cpu().numpy())
    
    print("\nTest completed!")


if __name__ == "__main__":
    main() 