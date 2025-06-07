#!/bin/bash

echo "GPU Embedding Test Setup"
echo "========================"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Run the test
echo -e "\nRunning GPU embedding test...\n"
python embedding_gpu_test.py 