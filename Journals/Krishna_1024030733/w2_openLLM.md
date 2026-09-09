# Week 2: Open-Source LLM Research and Qwen Model Setup

## Work Completed

During Week 2, I focused on researching suitable **open-source Large Language Models (LLMs)** that could be used for our coding benchmark evaluation. The main objective was to identify a model that provides good code-generation capabilities while also being practical to run locally on available hardware.

### Research on Open-Source LLMs

I researched and compared several open-source LLMs that are suitable for **code generation and programming-related tasks**.

The comparison focused on factors such as:

* Coding and reasoning capabilities.
* Number of parameters and computational requirements.
* Availability of different model sizes.
* Support for local inference.
* Compatibility with tools such as **Ollama**.
* Inference speed and resource requirements.
* Suitability for automated coding benchmark evaluation.
* Ability to generate executable and reliable code.

During this research, I came across the **Qwen2.5-Coder** family of models, which is specifically designed and optimized for coding-related tasks. The availability of multiple parameter sizes made it particularly suitable for our project, as different versions could be tested under different computational constraints.

### Selection of Qwen2.5-Coder

After researching the available options, I selected the **Qwen2.5-Coder** model family as a suitable choice for our coding benchmark experiments.

A major advantage of the Qwen2.5-Coder family was the availability of multiple model sizes. This allows us to study how **model size and parameter count affect code-generation performance** while keeping the underlying model family consistent.

The models can also be run locally, which is useful for our project because it allows us to perform experiments without depending entirely on external APIs or cloud-based inference services.

### Distribution of Model Versions

To enable parallel experimentation within the team, I distributed **three different versions of the Qwen model** among my team members.

Each team member could work with a different parameter configuration and evaluate the model under the same general benchmark methodology.

This setup allows us to later compare the relationship between:

**Model Size → Computational Requirements → Inference Performance → Coding Accuracy**

It also provides a foundation for investigating whether larger models consistently provide better results on coding benchmark problems.

### Qwen2.5-Coder 7B Setup

For my individual experimentation, I selected the **Qwen2.5-Coder 7B** parameter version and installed it on my PC.

I configured the required local environment and verified that the model was available for local inference.

The 7B model was selected to provide a stronger coding model for experimentation while still remaining practical to run on a local machine.

The local inference workflow was established as:

**Coding Problem → Prompt → Qwen2.5-Coder 7B → Generated Code → Code Processing → Evaluation**

### Initial Model Testing

After installing the model, I performed initial tests using programming-oriented prompts to verify that the model was functioning correctly and generating usable code.

The testing focused on:

* Checking whether the model correctly understood programming requirements.
* Verifying that the generated responses contained valid code.
* Checking whether the generated code could be extracted from the model response.
* Evaluating whether the model could handle different types of programming problems.
* Understanding the practical requirements for integrating the model with the benchmark evaluator.

These initial tests helped establish the model environment that will be used for subsequent benchmark evaluation and experimentation.

### Key Observation

The research and setup phase highlighted that **model parameter size is an important factor when evaluating coding LLMs**.

Having multiple versions of the Qwen2.5-Coder family available provides an opportunity to perform controlled comparisons between models of different sizes.

This will allow the project to investigate whether increasing model size leads to consistently better code-generation accuracy, or whether smaller models can perform competitively on specific categories of programming problems.

## Outcome

By the end of Week 2:

* Researched and compared multiple **open-source LLMs** suitable for code-generation tasks.
* Identified the **Qwen2.5-Coder** family as a suitable model for the project.
* Studied different parameter-size variants of the Qwen model.
* Distributed **three different Qwen model versions** among team members for parallel experimentation.
* Installed and configured the **Qwen2.5-Coder 7B** model on my PC.
* Verified that the model was functioning correctly for local inference.
* Performed initial code-generation tests using programming prompts.
* Established the local model environment required for further benchmark experiments.
* Identified **model size and parameter count** as important variables for comparative evaluation.
* Prepared the Qwen2.5-Coder 7B setup for integration with the coding benchmark evaluation pipeline.
