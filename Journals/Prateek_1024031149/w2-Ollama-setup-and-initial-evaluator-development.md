# Week 2: Ollama Setup and Initial Evaluator Development

## Work Completed

During Week 2, I started implementing the coding benchmark evaluator based on the evaluation methodology planned during Week 1.

### Ollama and Qwen2.5-Coder Setup

Set up **Ollama** as the local model-serving environment for running coding LLMs.

Installed the **Qwen2.5-Coder 1.5B** model and verified that it was working correctly:

```powershell
ollama pull qwen2.5-coder:1.5b
```

Tested the model with a basic Python coding prompt:

```powershell
ollama run qwen2.5-coder:1.5b "write a python function to reverse a string"
```

The model successfully generated a Python solution, confirming that the local inference environment was functioning correctly.

### Initial Evaluator Development

Started developing an automated evaluator for testing LLM-generated code against coding benchmark problems.

The initial evaluator focused on:

* Loading coding problems from a JSONL benchmark dataset.
* Sending individual problem prompts to the Qwen2.5-Coder model through Ollama.
* Receiving and processing model-generated responses.
* Extracting Python code from the generated responses.
* Supporting both **function-based** and **stdin/stdout-based** problems.
* Preparing generated code for automated execution.
* Running solutions against the provided test cases.
* Recording evaluation results for each problem.

The evaluator was designed to process problems **individually**, allowing results to be saved progressively instead of waiting for the entire benchmark to finish.

### Dataset Integration

Worked on organizing and preparing the coding benchmark dataset so that its structure could be consumed consistently by the evaluator.

The dataset structure was designed to provide the necessary information for generating prompts, executing solutions, and evaluating their correctness.

### Key Observation

The initial evaluator established the core pipeline connecting:

**Benchmark Dataset → Ollama → Qwen2.5-Coder → Generated Code → Test Execution → Evaluation Results**

This provided the foundation for scaling the evaluation to larger benchmark datasets and multiple coding models.

## Outcome

By the end of Week 2:

* Ollama was successfully configured as the local inference environment.
* Qwen2.5-Coder 1.5B was installed and tested successfully.
* The initial evaluator pipeline was implemented.
* Support for different coding problem formats was added.
* The benchmark dataset was integrated with the evaluator.
* The system was prepared for larger-scale automated model evaluation.
