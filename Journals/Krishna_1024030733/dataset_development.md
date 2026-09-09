Week: Benchmark Dataset Construction
Work Completed
During this week, I built the coding benchmark dataset that the evaluator would later run against. The main focus was sourcing problems from established coding benchmarks, normalizing them into a single unified format, and verifying every problem so that the benchmark could be evaluated automatically and reproducibly.

Dataset Sourcing
Rather than inventing problems, I assembled the benchmark from four established, publicly available coding datasets so that the problems, tests, and metadata came from trusted sources.

The sources used were:

MBPP (google-research-datasets/mbpp)
HumanEval+ (evalplus/humanevalplus)
APPS (codeparrot/apps)
CodeContests (deepmind/code_contests)
Each dataset was loaded through the Hugging Face datasets library. Because the newer library version no longer supports dataset loading scripts, APPS and CodeContests were loaded from their auto-converted parquet mirrors:

load_dataset("codeparrot/apps", revision="refs/convert/parquet")
Schema Normalization
All problems were normalized into a single JSONL schema so that the evaluator could treat every problem uniformly. Each record used exactly these fields:

{
  "problem_id": "...",
  "source": "...",
  "task_type": "...",
  "prompt": "...",
  "tests": [...],
  "reference_solution": "...",
  "human_difficulty": "..."
}
The dataset was designed to distinguish two evaluation styles through the task_type field:

function — MBPP and HumanEval+ problems, where the model implements a callable Python function and tests are executable assertions.
stdin_stdout — APPS and CodeContests problems, where the program reads from standard input and writes to standard output and tests are {input, expected} pairs.
Prompts were normalized for consistency without changing the underlying problem requirements, and difficulty metadata was mapped into consistent categories (easy, medium, hard, interview, competition), using null where the source provided no rating.

Reference Solution Verification
Since the benchmark is meant to be graded automatically, every problem needed reliable, deterministic tests. To guarantee this, each problem's reference solution was executed against its own tests, and only problems whose reference solution reproduced the expected results were kept.

The verification distinguished the two task types:

Function problems — the reference solution was executed and each assertion was run.
Stdin/stdout problems — the reference solution was run with each test input and its output was compared against the expected output after trailing-whitespace normalization.
This execution-based filtering also automatically removed non-deterministic problems, problems with multiple valid outputs, and special-judge problems, since their reference solutions could not reproduce a single fixed expected output.

Sandboxed Execution for Verification
Because verification runs untrusted solution code at scale, execution was isolated in a dedicated worker process rather than run inline. This was important after an early in-process approach caused runaway solutions to spawn background threads that could not be terminated, which starved later executions and produced cascading false failures. Moving each execution into an isolated, killable worker made verification both correct and fast.

The verification pipeline was:

Source Dataset (MBPP / HumanEval+ / APPS / CodeContests)
       ↓
Schema Normalization
       ↓
Reference Solution + Tests
       ↓
Isolated Worker Execution (timeout enforced)
       ↓
Output / Assertion Comparison
       ↓
Keep (verified) or Exclude (with reason)
Composition, Balancing and Edge Cases
The dataset was assembled to a fixed total with a useful difficulty spread within each source. Handling the real limits of each source required several decisions:

HumanEval+ contains only 164 problems (a fixed benchmark size), so the requested count could not be met from that source alone; the shortfall was reallocated to MBPP instead of fabricating problems.
One HumanEval+ problem was excluded as non-deterministic (a floating-point root-finder).
APPS call-based problems were excluded by design, since APPS was mapped to stdin/stdout; because the APPS training split contains few pure stdin/stdout problems, additional problems were drawn from the APPS test split.
CodeContests reference solutions were restricted to official accepted Python 3 submissions, and difficulty was derived from Codeforces rating.
Validation and Manifest
Before finalizing, the full dataset was validated end to end: valid JSON on every line, unique problem IDs, correct source and task-type mapping, non-empty prompts and tests, tests matching the prompt, and confirmation that no reference solution leaked into a prompt. A random sample was independently re-executed to confirm the written file was intact.

A dataset manifest was also generated, recording:

Total problem count
Per-source counts
Task-type counts
Difficulty distribution
Excluded problems and the reason for each exclusion
A validation summary
Key Observation
Verifying every reference solution by execution — rather than trusting the source tests blindly — was the single most important step. It surfaced broken fixtures, non-deterministic problems, and unusable test cases that would otherwise have silently corrupted the benchmark results later.

Isolating that execution in a killable worker process was equally important: without it, a single runaway solution could poison later verifications and produce misleading failure counts.

Outcome
By the end of this week:

A 1,500-problem benchmark dataset was assembled from four established sources.
All problems were normalized into a single JSONL schema with a consistent metadata format.
Both function-based and stdin/stdout-based problem types were supported and clearly separated.
Every included problem's reference solution was executed and verified against its tests.
Non-deterministic and unusable problems were excluded and documented.
A dataset manifest with counts, distributions, exclusions, and a validation summary was produced.
The dataset was now clean, reproducible, and ready to be run through the evaluator against the Qwen2.5-Coder models.
