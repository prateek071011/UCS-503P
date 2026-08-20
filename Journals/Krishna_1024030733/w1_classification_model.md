# Week 1 : Project Structure, Prompt Classification Methods, and Dataset Selection

## Project Structure Completed

Finalized the overall project file and folder structure to provide a clear and organized foundation for the implementation of the gating and routing system.

The prompt classification method was also finalized. **MiniLM** was selected as the initial classification approach because it is lightweight, based on the Transformer architecture, and can be executed locally with relatively low computational requirements.

For the initial dataset, **HumanEval** and **MBPP (Mostly Basic Python Problems)** were selected. These datasets provide a suitable starting point for evaluating coding prompts and developing the initial gating router.

## Work Completed

Researched different approaches for language and prompt classification to determine a suitable method for categorizing coding prompts before they are passed to the routing system.

Among the approaches considered, **MiniLM** was identified as a suitable method for the project because it uses a Transformer-based architecture while remaining lightweight enough to run locally. It can be used to generate semantic representations of prompts and group or classify them based on their characteristics and coding requirements.

The initial datasets were also finalized based on their suitability for coding-task classification and model evaluation.

## Key Observation

Datasets such as **HumanEval** and **MBPP** provide a useful collection of coding problems, prompts, and corresponding code solutions. These datasets cover a range of programming tasks and provide a structured foundation for developing and testing the initial gating router.

Using these datasets can help the router learn the characteristics of different coding prompts and identify patterns that may be useful when deciding which candidate model should handle a particular task.

They also provide an initial code base that can be used to generate routing data by evaluating how different candidate models perform on the same set of prompts.

## Project Direction

Based on the research and decisions made during this phase, a preliminary architecture for the gating model can now be developed.

The initial implementation will focus on using **MiniLM for prompt classification**, followed by the gating/routing component that can use the classified prompt information to assist in selecting an appropriate candidate LLM.

The selected datasets, HumanEval and MBPP, will serve as the initial source of coding prompts for training and evaluating the routing system. This provides a practical starting point for moving from the research and planning stage toward the actual implementation and training of the gating model.

## Next Steps

* Finalize the dataset categories.
* Select the candidate models.
* Collect model responses for the initial dataset.
* Define response-quality metrics.
* Record token usage for each model.
* Begin implementation of the initial gating model.
* Train and evaluate the classifier using the selected datasets.
