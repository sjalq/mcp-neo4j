#!/usr/bin/env python3
"""
Test the best open-source embedding models on GPU
Comparing performance and quality across different models
"""

import torch
import time
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Tuple
import gc

# Test sentences for semantic similarity
TEST_SENTENCES = [
    # Similar pairs
    ("The cat sat on the mat", "A feline rested on the rug"),
    ("I love machine learning", "Machine learning is my passion"),
    ("The weather is beautiful today", "It's a lovely day outside"),
    
    # Different topics
    ("The cat sat on the mat", "Machine learning is my passion"),
    ("I love pizza", "The stock market crashed today"),
    
    # Technical similarity
    ("Neural networks process information", "Deep learning models analyze data"),
    ("GPU acceleration speeds up training", "Graphics cards improve model performance"),
]

# Top open-source models to test
MODELS = [
    {
        "name": "all-MiniLM-L6-v2",
        "dimension": 384,
        "description": "Small, fast, good general purpose"
    },
    {
        "name": "BAAI/bge-base-en-v1.5",
        "dimension": 768,
        "description": "Top performer on MTEB benchmark"
    },
    {
        "name": "BAAI/bge-large-en-v1.5", 
        "dimension": 1024,
        "description": "Larger BGE model, higher quality"
    },
    {
        "name": "nomic-ai/nomic-embed-text-v1.5",
        "dimension": 768,
        "description": "8192 token context, strong performance"
    },
    {
        "name": "thenlper/gte-base",
        "dimension": 768,
        "description": "Alibaba's General Text Embeddings"
    }
]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors"""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def test_model(model_name: str, device: str = 'cuda') -> Dict:
    """Test a single embedding model"""
    print(f"\n{'='*60}")
    print(f"Testing: {model_name}")
    print('='*60)
    
    try:
        # Load model
        print("Loading model...")
        start_load = time.time()
        model = SentenceTransformer(model_name, device=device)
        load_time = time.time() - start_load
        print(f"✓ Model loaded in {load_time:.2f} seconds")
        
        # Get model info
        if hasattr(model[0], 'auto_model'):
            param_count = sum(p.numel() for p in model[0].auto_model.parameters())
            print(f"✓ Parameters: {param_count/1e6:.1f}M")
        
        # Prepare test data
        all_sentences = []
        for pair in TEST_SENTENCES:
            all_sentences.extend(pair if isinstance(pair, tuple) else [pair])
        
        # Warmup
        print("\nWarming up...")
        _ = model.encode(["warmup sentence"], convert_to_tensor=True)
        if device == 'cuda':
            torch.cuda.synchronize()
        
        # Test encoding speed
        print("\nTesting encoding speed...")
        test_batch = all_sentences * 100  # Create larger batch
        
        start_time = time.time()
        embeddings = model.encode(test_batch, convert_to_tensor=True, show_progress_bar=False)
        
        if device == 'cuda':
            torch.cuda.synchronize()
        
        encode_time = time.time() - start_time
        throughput = len(test_batch) / encode_time
        
        print(f"✓ Encoded {len(test_batch)} sentences in {encode_time:.3f} seconds")
        print(f"✓ Throughput: {throughput:.1f} sentences/second")
        
        # Test semantic similarity
        print("\nTesting semantic similarity...")
        similarities = []
        
        for i, (sent1, sent2) in enumerate(TEST_SENTENCES[:3]):  # Similar pairs
            emb1 = model.encode(sent1, convert_to_tensor=True)
            emb2 = model.encode(sent2, convert_to_tensor=True)
            sim = torch.cosine_similarity(emb1.unsqueeze(0), emb2.unsqueeze(0)).item()
            similarities.append(sim)
            print(f"  Similar pair {i+1}: {sim:.4f}")
        
        for i, (sent1, sent2) in enumerate(TEST_SENTENCES[3:5]):  # Different pairs
            emb1 = model.encode(sent1, convert_to_tensor=True)
            emb2 = model.encode(sent2, convert_to_tensor=True)
            sim = torch.cosine_similarity(emb1.unsqueeze(0), emb2.unsqueeze(0)).item()
            similarities.append(sim)
            print(f"  Different pair {i+1}: {sim:.4f}")
        
        avg_similar = np.mean(similarities[:3])
        avg_different = np.mean(similarities[3:5])
        separation = avg_similar - avg_different
        
        print(f"\n  Average similarity (similar pairs): {avg_similar:.4f}")
        print(f"  Average similarity (different pairs): {avg_different:.4f}")
        print(f"  Separation score: {separation:.4f}")
        
        # Memory usage
        if device == 'cuda':
            mem_allocated = torch.cuda.memory_allocated() / 1024**2
            mem_reserved = torch.cuda.memory_reserved() / 1024**2
            print(f"\nGPU Memory: {mem_allocated:.1f} MB allocated, {mem_reserved:.1f} MB reserved")
        
        # Cleanup
        del model
        gc.collect()
        if device == 'cuda':
            torch.cuda.empty_cache()
        
        return {
            "name": model_name,
            "load_time": load_time,
            "throughput": throughput,
            "avg_similar": avg_similar,
            "avg_different": avg_different,
            "separation": separation,
            "success": True
        }
        
    except Exception as e:
        print(f"✗ Error testing {model_name}: {str(e)}")
        return {
            "name": model_name,
            "success": False,
            "error": str(e)
        }


def main():
    print("=== Best Open-Source Embedding Models Test ===\n")
    
    # Check GPU
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"CUDA: {torch.version.cuda}")
        device = 'cuda'
    else:
        print("No GPU available, using CPU")
        device = 'cpu'
    
    # Test each model
    results = []
    for model_info in MODELS:
        result = test_model(model_info["name"], device)
        result["description"] = model_info["description"]
        result["dimension"] = model_info["dimension"]
        results.append(result)
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY - Best Open-Source Embedding Models")
    print("="*80)
    
    successful_results = [r for r in results if r["success"]]
    
    if successful_results:
        # Sort by throughput
        by_speed = sorted(successful_results, key=lambda x: x["throughput"], reverse=True)
        print("\n🚀 Fastest Models:")
        for i, r in enumerate(by_speed[:3], 1):
            print(f"{i}. {r['name']}: {r['throughput']:.1f} sentences/sec")
        
        # Sort by quality (separation score)
        by_quality = sorted(successful_results, key=lambda x: x["separation"], reverse=True)
        print("\n🎯 Best Quality Models (semantic separation):")
        for i, r in enumerate(by_quality[:3], 1):
            print(f"{i}. {r['name']}: {r['separation']:.4f} separation score")
        
        # Best overall (balance of speed and quality)
        for r in successful_results:
            # Normalize scores
            r["speed_score"] = r["throughput"] / max(x["throughput"] for x in successful_results)
            r["quality_score"] = r["separation"] / max(x["separation"] for x in successful_results)
            r["overall_score"] = (r["speed_score"] + r["quality_score"]) / 2
        
        by_overall = sorted(successful_results, key=lambda x: x["overall_score"], reverse=True)
        print("\n⭐ Best Overall (speed + quality):")
        for i, r in enumerate(by_overall[:3], 1):
            print(f"{i}. {r['name']} (dim={r['dimension']})")
            print(f"   {r['description']}")
            print(f"   Speed: {r['throughput']:.1f} sent/s, Quality: {r['separation']:.4f}")
    
    print("\n✅ Test completed!")


if __name__ == "__main__":
    main() 