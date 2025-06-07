# GPU Embedding Model Experiments

This folder contains experiments testing various text embedding models on GPU.

## Files

### Core Tests
- `embedding_gpu_test.py` - Basic GPU test with synthetic embedding model
- `simple_gpu_test.py` - GPU detection and capability test
- `test_best_embeddings.py` - Comprehensive test of top open-source models
- `test_bge_large_resources.py` - Resource usage analysis for BGE-large model
- `local_embedding_example.py` - Example using BAAI/bge-base-en-v1.5 locally

### Setup
- `requirements.txt` - Python dependencies
- `run_test.sh` - Setup script for virtual environment

## Key Findings

### Best Open-Source Models
1. **Overall**: BAAI/bge-base-en-v1.5 (109M params, best balance)
2. **Speed**: all-MiniLM-L6-v2 (22.7M params, 2656 sent/s)
3. **Quality**: BAAI/bge-large-en-v1.5 (335M params)
4. **Multilingual**: multilingual-e5-large-instruct (560M params)

### GPU Requirements (RTX 5060 Ti)
- PyTorch nightly with CUDA 12.8 required for RTX 50 series
- Install: `pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128`

### Performance on RTX 5060 Ti
- all-MiniLM-L6-v2: 2,656 sentences/sec, 98MB GPU memory
- bge-base-en-v1.5: 1,959 sentences/sec, 430MB GPU memory  
- bge-large-en-v1.5: 1,184 sentences/sec, 1.3GB GPU memory

## Usage

```bash
# Run basic GPU test
python embedding_gpu_test.py

# Test best embedding models
python test_best_embeddings.py

# Check BGE-large resource usage
python test_bge_large_resources.py
``` 