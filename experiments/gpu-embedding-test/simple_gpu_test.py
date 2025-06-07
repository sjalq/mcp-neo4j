#!/usr/bin/env python3
"""
Simple GPU availability test without heavy dependencies
"""

import subprocess
import sys
import platform

def check_nvidia_smi():
    """Check if nvidia-smi is available"""
    try:
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ NVIDIA GPU detected via nvidia-smi")
            print("\nGPU Info:")
            # Get just the GPU name
            subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'])
            return True
        else:
            print("✗ nvidia-smi command failed")
            return False
    except FileNotFoundError:
        print("✗ nvidia-smi not found - No NVIDIA GPU detected")
        return False

def check_cuda():
    """Check CUDA availability"""
    try:
        result = subprocess.run(['nvcc', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("\n✓ CUDA compiler found:")
            print(result.stdout.split('\n')[3])  # Get version line
            return True
        else:
            print("\n✗ CUDA compiler (nvcc) not found")
            return False
    except FileNotFoundError:
        print("\n✗ CUDA compiler (nvcc) not found")
        return False

def main():
    print("=== Simple GPU Detection Test ===")
    print(f"System: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version.split()[0]}")
    print()
    
    has_gpu = check_nvidia_smi()
    has_cuda = check_cuda()
    
    print("\n=== Summary ===")
    if has_gpu and has_cuda:
        print("✓ GPU and CUDA are available for ML workloads")
    elif has_gpu:
        print("⚠ GPU detected but CUDA not properly installed")
    else:
        print("✗ No GPU detected - will use CPU for ML workloads")
    
    # Try importing common ML libraries if available
    print("\n=== ML Library GPU Support ===")
    
    # Check PyTorch
    try:
        import torch
        print(f"PyTorch {torch.__version__}: CUDA {'available' if torch.cuda.is_available() else 'not available'}")
        if torch.cuda.is_available():
            print(f"  Device: {torch.cuda.get_device_name(0)}")
    except ImportError:
        print("PyTorch: not installed")
    
    # Check TensorFlow
    try:
        import tensorflow as tf
        gpus = tf.config.list_physical_devices('GPU')
        print(f"TensorFlow {tf.__version__}: {len(gpus)} GPU(s) detected")
        for gpu in gpus:
            print(f"  Device: {gpu.name}")
    except ImportError:
        print("TensorFlow: not installed")

if __name__ == "__main__":
    main() 