# ACOS Benchmark

A/B benchmark comparing a **bare** assistant prompt (ARM A) against the **ACOS**
per-category reasoning-kernel prompts (ARM B) across a fixed set of Hebrew operator
tasks. Each task is run through both arms, graded blind by an LLM judge against
per-task gold criteria, and tagged with a failure taxonomy.

## Layout

```
acos-benchmark/
├── benchmark_tasks.jsonl     # the tasks (one JSON object per line)
├── bare_prompt.txt           # ARM A system prompt (the control)
├── arm_b_prompts/            # ARM B system prompts, one per category
│   ├── acos_C-FND.txt        #   foundation / prioritization
│   ├── acos_C-SLS.txt        #   sales
│   ├── acos_C-AISD.txt       #   AI-systems design
│   ├── acos_C-ARCH.txt       #   software architecture
│   ├── acos_C-DEC.txt        #   decisions
│   ├── acos_C-RES.txt        #   research
│   └── acos_C-COM.txt        #   marketing / copy
├── run_benchmark.py          # step 1: generate responses  -> results.jsonl
├── judge_results.py          # step 2: grade responses     -> judged_results.jsonl
├── .env.example              # copy to .env, add your key
├── .gitignore
└── README.md
```

## Setup

Requires Python 3.9+ and two packages:

```bash
pip install anthropic python-dotenv
```

Provide your Anthropic API key via a `.env` file (git-ignored, never committed):

```bash
cp .env.example .env
# then edit .env and set:
# ANTHROPIC_API_KEY=sk-ant-...
```

Both scripts exit immediately with a clear error if `ANTHROPIC_API_KEY` is unset.

## Usage

Run from inside this folder (the scripts default to the files here).

### 1. Generate responses

```bash
python run_benchmark.py --model claude-sonnet-4-6
```

For each task, runs **ARM A (bare)** and **ARM B (ACOS)**, **3 runs each**, at
`temperature 0`. ARM B picks the prompt file matching the task's `cat`
(`arm_b_prompts/acos_<cat>.txt`). The user message sent to the model is the task's
`input` followed by its `prompt`. Results are appended to `results.jsonl`.

With 20 tasks this is `20 × 2 arms × 3 runs = 120` model calls.

### 2. Grade responses

```bash
python judge_results.py --judge-model claude-opus-4-8
```

Grades every row in `results.jsonl` against its task's gold criteria and appends to
`judged_results.jsonl`. The judge grades **blind** — it never sees which arm produced
a response.

## Flags

**`run_benchmark.py`**

| flag | default | meaning |
|------|---------|---------|
| `--model` | *(required)* | model id, e.g. `claude-sonnet-4-6` |
| `--tasks` | `benchmark_tasks.jsonl` | tasks file |
| `--bare` | `bare_prompt.txt` | ARM A system prompt |
| `--acos-dir` | `arm_b_prompts` | dir of `acos_<cat>.txt` ARM B prompts |
| `--out` | `results.jsonl` | output file (appended) |
| `--max-tokens` | `1024` | max output tokens per call |

**`judge_results.py`**

| flag | default | meaning |
|------|---------|---------|
| `--judge-model` | *(required)* | judge model id, e.g. `claude-opus-4-8` |
| `--tasks` | `benchmark_tasks.jsonl` | tasks file (for gold criteria) |
| `--results` | `results.jsonl` | responses to grade |
| `--out` | `judged_results.jsonl` | output file (appended) |
| `--max-tokens` | `1024` | max output tokens per judge call |

## Data formats

**Task** (`benchmark_tasks.jsonl`, one per line) — required fields `id`, `cat`,
`input`, `prompt`; also carries `gold` (criteria `G1`–`G4`), `trap`, and `word_cap`.

**Result row** (`results.jsonl`):

```json
{"task_id": "...", "cat": "...", "arm": "A|B", "run_n": 1,
 "output_text": "...", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
```

**Judged row** (`judged_results.jsonl`):

```json
{"task_id": "...", "cat": "...", "arm": "A|B", "run_n": 1,
 "G1": true, "G2": true, "G3": true, "G4": true,
 "fail_tags": [], "catastrophic": false, "reasons": {}}
```

### Failure taxonomy

The judge assigns one tag per failed criterion:

- **F1 CONFAB** — invented data (number, quote, stage, source, fact not in the input)
- **F2 WRONG-FRAME** — solved a different problem than asked
- **F3 GENERIC** — template answer; could be written without reading the input
- **F4 SKIPPED-CHECK** — proceeded past missing/blocking information silently
- **F5 OVERBUILD** — scope inflation / solved beyond the ask
- **F6 STAGE-VIOLATION** — pitched/priced/built ahead of evidence
- **F7 NO-COMMIT** — vague next step
- **F8 BUDGET-BLOWN** — output exceeds `2 × word_cap` (computed deterministically, not by the judge)

A row is flagged `catastrophic` when `G2` fails (fabrication), or when `G1` fails on a
high-stakes task (`DEC-01`, `RES-01`, `SLS-03`, `SLS-04`).

## Resume behavior

Both scripts are **resume-safe** and append-only: a completed `(task_id, arm, run_n)`
row is skipped on restart, so an interrupted run can simply be re-invoked. Both stop
immediately (fatal) on any Anthropic API error. Delete the output file to start fresh.
