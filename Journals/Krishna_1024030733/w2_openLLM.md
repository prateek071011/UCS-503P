Week 2: Open-Source LLM Research and Qwen Model Setup

Work Completed

During Week 2, I focused on researching suitable open-source Large Language Models (LLMs) that could be integrated into our coding benchmark evaluation framework. The primary objective was to identify a model that could generate code effectively while also being practical to run locally using available computational resources.

Research on Open-Source LLMs

I researched and compared several open-source LLMs that are suitable for code generation and programming-related tasks.

The comparison focused on factors such as:

Coding and reasoning capabilities.

Number of parameters and computational requirements.

Availability of models for local inference.

Compatibility with frameworks such as Ollama.

Response quality for programming problems.

Inference speed and memory requirements.

Availability of different model sizes for experimentation.

Suitability for automated benchmark evaluation.

During this research, I came across the Qwen2.5-Coder family of models, which is specifically optimized for coding-related tasks. The availability of multiple parameter sizes made it particularly suitable for our project because different versions could be tested under different hardware and performance constraints.

Selection of Qwen2.5-Coder

After evaluating the available options, I selected the Qwen2.5-Coder model family as one of the primary models for our coding benchmark experiments.

One of the major advantages was the availability of multiple model sizes, allowing us to investigate how model scale affects code-generation performance while keeping the overall evaluation methodology consistent.

The model family also provided a practical option for local inference, which is important for our evaluation pipeline because it allows us to run experiments without depending entirely on external API services.

Distribution of Model Versions Among Team Members

To allow the team to experiment with different model configurations in parallel, I distributed three different Qwen model versions among the team members.

This allowed different members to work with different parameter scales and configurations while following the same general evaluation methodology.

The distribution also helped us compare:

Model Size → Computational Requirements → Inference Behaviour → Coding Performance

This provided a basis for studying whether increasing the number of model parameters resulted in improvements in code-generation quality and benchmark performance.

Qwen2.5-Coder 7B Setup

For my individual experimentation, I selected and installed the Qwen2.5-Coder 7B parameter version on my PC.

I configured the local environment required to run the model and verified that the model could successfully perform code-generation tasks.

The setup enabled me to generate programming solutions locally and provided the foundation for integrating the model with the automated evaluator developed for the benchmark.

The local inference workflow can be represented as:

Coding Problem → Prompt → Qwen2.5-Coder 7B → Generated Code → Code Extraction → Test Execution → Evaluation Result

Initial Model Testing

After installation, I performed initial tests using programming-oriented prompts to verify that the model was generating usable code.

The testing focused on checking:

Whether the model correctly understood programming requirements.

Whether generated responses contained executable code.

Whether the output format could be processed by an automated evaluator.

Whether the model could handle different types of coding problems.

Whether the generated solutions could be extracted and executed independently.

These initial experiments helped identify practical considerations that would need to be handled during the later development of the benchmark evaluation pipeline.

Key Observation

The research and setup phase showed that model parameter size is an important experimental variable when evaluating coding LLMs.

Using multiple versions of the Qwen2.5-Coder family provides an opportunity to perform controlled comparisons while keeping the underlying model family consistent.

This will allow the project to investigate whether larger models consistently produce more correct and reliable solutions, or whether smaller models can achieve comparable performance on certain categories of programming problems.

Outcome

By the end of Week 2:

Researched and compared multiple open-source LLMs suitable for code-generation tasks.

Identified the Qwen2.5-Coder family as a suitable candidate for the project.

Studied different parameter-size variants of the model.

Distributed three Qwen model versions among team members for parallel experimentation.

Installed and configured the Qwen2.5-Coder 7B model on my local PC.

Verified that the model was capable of generating programming solutions.

Established the local inference environment required for subsequent benchmark experiments.

Identified model size/parameter count as an important variable for future comparative evaluation.

Prepared the Qwen2.5-Coder 7B setup for integration with the automated coding benchmark evaluator.
