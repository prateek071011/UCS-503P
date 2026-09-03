# Coding Benchmark Evaluator

Evaluates code-generation models using Ollama and
Docker-based sandboxed execution.

## Requirements

- Python 3.x
- Docker
- Ollama
- A supported coding model

## Setup

1. Install dependencies
2. Pull the desired Ollama model
3. Build the Docker image

## Run

python evaluate_ollama_docker.py \
    --dataset ../dataset/coding_benchmark.jsonl \
    --model qwen2.5-coder:1.5b \
    --output ../results/qwen_1.5b.jsonl

## Evaluation

The evaluator:
- sends each problem to Ollama
- extracts generated code
- executes it inside Docker
- runs the benchmark tests
- classifies failures
- records token and timing metrics
- saves results incrementally
- supports resuming interrupted evaluations
