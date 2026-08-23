# ROSCon 2026: Local Robot Inference

Complete the notebooks in order:

1. `02_local_inference_with_lemonade.ipynb`
2. `03_robot_agents.ipynb`
3. `04_code_as_policies_with_capx.ipynb`
4. `05_repository_as_policy_with_rho.ipynb`
5. `06_evolving_rai_for_o3de.ipynb`

Notebook 05 runs one bounded HELIX/OpenCode mutation against a small CaP-X
repository. It demonstrates RHO's repository-as-policy loop with local models;
it is not a reproduction of the paper's full training run.

Notebook 06 applies the same one-generation repository-evolution pattern to a
live RAI tool-calling agent. A deterministic in-memory tabletop replaces the
full O3DE benchmark so it fits the workshop: HELIX edits both `prompt.py` and
`tools.py`, the notebook displays the selected files, and RAI reruns one
held-out manipulation test. It does not replay or claim to reproduce paper
results.

## Script-first proof

The workshop story can be validated before converting it into notebook cells.
The default live path uses small Gemma E4B for one-shot CaP-X generation and
local Qwen3 Coder 30B-A3B for the HELIX/OpenCode mutation:

```bash
/opt/capx-venv/bin/python /ryzers/notebooks/workshop_story.py \
  --source live \
  --generations 1 \
  --max-attempts 3 \
  --show-primitives \
  --capture-video \
  --require-improvement \
  --output-dir /tmp/capx-rho-story
```

The code-specialized model is deliberate: live testing found Gemma E4B useful
for producing the mixed-quality CaP-X examples, but unreliable at emitting
OpenCode edit-tool calls. Pass `--rho-model Gemma-4-E4B-it-GGUF` to test the
all-Gemma variant. The report records both model names.

For a simulator-free plumbing check, replay the explicitly labeled authentic
failed trial and use the deterministic mock evaluator:

```bash
/opt/capx-venv/bin/python /ryzers/notebooks/workshop_story.py \
  --source recorded \
  --mock-rho \
  --prepare-only
```

`capx_story.py` can also run either half independently. Every output manifest
states whether it came from a live run or a recorded fixture; recorded output is
never presented as a live model result.

## Five-trial generalization check

`generalization_eval.py` holds each policy file byte-for-byte constant while
evaluating it over independently reset trial IDs. A live five-trial run found:

- cube-stack before/after RHO: 0/5 to 3/5 completed, with execution failures
  reduced from 5 to 0
- cube lift: 4/5 completed
- spill wipe: 1/5 completed
- cube restack: 0/5 before and after the accepted missing-import repair; RHO
  reduced execution failures from 5 to 0 but did not repair task strategy

The compact, tracked result is
`fixtures/capx_rho_generalization_5_trials.json`. Full evaluator feedback is
written under `experiment_results/generalization-20260822/`.

Notebook 05 now performs a separate paired experiment: it samples five held-out
seed/trial IDs once, runs the frozen cube-stack policy before evolution, evolves
with HELIX/OpenCode, and reruns the same seeds. Its end-to-end validation run
observed 0/5 to 4/5 task completion and 5 to 0 execution failures. The executed
notebook and JSON report are saved under `experiment_results/`.

Example:

```bash
/opt/capx-venv/bin/python /ryzers/notebooks/generalization_eval.py \
  --policy after:cube_stack:/path/to/repaired/program.py \
  --trials 1,2,3,4,5 \
  --output /tmp/cube-stack-generalization.json
```

`task_repair.py` applies the same bounded HELIX/OpenCode workflow to a
task-specific CaP-X manifest. Its objective and mutation instructions are
explicit CLI inputs, and the manifest's authentic generation prompt becomes
the candidate API reference.

Environment checks:

```bash
/ryzers/test_ros.sh
/ryzers/test_o3de.sh
/ryzers/test_rai.sh
/ryzers/test_lemonade-sdk.sh
/ryzers/test_capx.sh
/ryzers/test_rho.sh
/ryzers/test_rai_toy_evolution.sh
```

The toy RAI evolution test is static/mock by default. Inside the
LocalInference image, opt into a real RAI seed-versus-repaired agent check:

```bash
RAI_TOY_RUN_LIVE=1 /ryzers/test_rai_toy_evolution.sh
```

The workshop's Gemma E2B, Gemma E4B, and Qwen3 Coder GGUFs are baked under
`/opt/lemonade-cache`, outside the JupyterHub home-volume mount. SAM2.1 Large
and OWLv2 Large are likewise baked under `/opt/capx-cache`; neither runtime
path needs a Hugging Face token or a first-run model download. Their
checkpoints are staged through FP16 before an on-device FP32 conversion to
avoid a multi-minute ROCm transfer while retaining FP32 execution. Matching
`*_fast.yaml` CaP-X configs retain SAM2.1 Small and OWLv2 Base for comparisons.
