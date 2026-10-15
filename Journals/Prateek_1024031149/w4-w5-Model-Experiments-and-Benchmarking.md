# Week 4: Model Experiments and Benchmarking

## Work Completed

During Week 4, I focused on experimenting with different code-generation LLMs, troubleshooting model execution, and evaluating their performance using the coding benchmark developed in the previous weeks.

### DeepSeek Model Experimentation

Initially, I attempted to use DeepSeek for code generation and evaluation. However, the setup did not work as expected, preventing me from proceeding with the planned benchmark run. I then explored alternative models that could be executed through Ollama in the available environment.

### Qwen2.5-Coder 3B Evaluation

After the initial DeepSeek attempt, I switched to Qwen2.5-Coder 3B and evaluated it using the project's 1,500-problem coding benchmark.

The evaluation produced the following results:

- Total benchmark problems: 1,500
- Validated passing solutions: 507
- Validated pass rate: 33.8%

These results established a baseline for comparing other models and understanding the limitations of the current code-generation setup.

### Benchmark Analysis

The benchmark includes problems from APPS, MBPP, HumanEval+, and CodeContests. I examined performance across different dataset sources and task formats, including function-based and stdin/stdout-based problems.

The results indicated substantial differences in performance across datasets and task formats. This highlighted the importance of using a diverse benchmark rather than relying on a small sample of coding problems.

### Evaluation Pipeline and Result Management

I continued working with the evaluator, JSONL dataset, checker specifications, and saved result files. The experiments emphasized the importance of consistent evaluation settings and preserving completed results during long-running benchmark executions.

## Challenges Faced

- The initial DeepSeek setup did not work as expected.
- Different coding models demonstrated different levels of accuracy.
- Long-running evaluations required careful management of saved results.
- Performance needed to be analyzed across multiple datasets and task formats.

## Learning Outcomes

- Gained practical experience running code-generation models through Ollama.
- Established a quantitative baseline for Qwen2.5-Coder 3B.
- Understood the importance of diverse benchmark datasets and consistent evaluation settings.
- Identified model correctness as a key factor in designing an efficient LLM routing system.

## Plan for the Next Week

- Evaluate smaller models, particularly Qwen2.5-Coder 1.5B.
- Compare model accuracy and inference efficiency.
- Improve the reliability of benchmark execution and result recovery.
- Use the collected measurements to guide the design of SAGE's model-routing strategy.

---

# Week 5: Smaller Model Evaluation and Experiment Management

## Work Completed

During Week 5, I focused on extending the model evaluation experiments, testing smaller coding models, configuring the Google Colab environment, and improving the handling of interrupted benchmark runs.

### Qwen2.5-Coder 3B Result Analysis

I reviewed the results obtained from the Qwen2.5-Coder 3B benchmark. The model achieved a validated pass rate of 33.8%, with 507 out of 1,500 problems passing the evaluation.

I also examined differences in performance across benchmark sources and task formats. This information will help inform the selection of suitable models for different categories of coding problems in SAGE.

### Qwen2.5-Coder 1.5B Experimentation

I started experimenting with Qwen2.5-Coder 1.5B to investigate the trade-off between model size, coding accuracy, and inference efficiency.

The smaller model was selected to determine whether it could handle simpler coding tasks with lower resource requirements than larger models. The benchmark was initiated using the existing dataset and evaluator.

The full evaluation was interrupted after approximately 500 problems, so the final accuracy and performance comparison remain pending.

### Google Colab and Google Drive Setup

I configured the project environment in Google Colab and connected Google Drive to access the benchmark files.

The project archive was extracted, and the required files were located, including:

- `evaluator.py`
- `dataset.jsonl`
- `checker_specs.json`
- Existing benchmark result files

I also checked GPU availability and addressed an installation issue involving the missing `zstd` dependency during Ollama setup.

### Resuming Interrupted Evaluations

The interruption highlighted the importance of preserving benchmark progress. I investigated the evaluator's resume functionality, which allows previously completed problem IDs to be skipped when the same output file and configuration are reused.

This approach helps avoid repeating completed evaluations and reduces unnecessary computation when long-running experiments are interrupted.

### Preparing for Comparative Evaluation

I continued preparing a consistent evaluation process for comparing models. The planned comparison considers correctness, generated token usage, inference latency, and computational requirements.

These measurements will provide a foundation for developing a routing strategy that selects models according to task requirements and measured performance.

## Challenges Faced

- The 1.5B benchmark was interrupted before all 1,500 problems were evaluated.
- Configuring the Google Colab environment required additional troubleshooting.
- Results needed to be preserved and resumed correctly to avoid unnecessary repeated computation.
- Smaller models may reduce resource consumption but can also sacrifice coding accuracy.

## Learning Outcomes

- Gained experience managing LLM benchmark experiments in Google Colab.
- Learned how resumable evaluation can preserve progress after interruptions.
- Improved understanding of the trade-off between model size, correctness, and inference efficiency.
- Identified the need for consistent experimental settings before comparing models.
