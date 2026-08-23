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
The default live path uses Gemma E4B for one-shot CaP-X generation and the
smaller Gemma E2B for HELIX/OpenCode mutation:

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

The smaller mutation model is deliberate. On the same one-generation repair,
Gemma E2B accepted the intended edit in 88.2 seconds and completed its held-out
rollout. Qwen3 Coder took 113.4 seconds and adds 17.3 GB to the image. Single
runs with Gemma E4B and Ministral 3B did not produce an accepted edit. These are
workshop measurements, not model-quality benchmarks.

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

Notebook 05 performs a separate paired experiment: it samples five held-out
seed/trial IDs once, runs the frozen cube-stack policy before evolution, evolves
with HELIX/OpenCode, and reruns the same seeds. The committed execution observed
0/5 to 5/5 task completion and 5 to 0 execution failures. It includes all five
post-evolution rollout videos.

Example:

```bash
/opt/capx-venv/bin/python /ryzers/notebooks/generalization_eval.py \
  --policy after:cube_stack:/path/to/repaired/program.py \
  --trials 1,2,3,4,5 \
  --output /tmp/cube-stack-generalization.json
```

`task_repair.py` applies the same bounded HELIX/OpenCode workflow to a
task-specific CaP-X manifest. Its objective and mutation instructions are
explicit CLI inputs, the manifest's authentic generation prompt becomes the
candidate API reference, and repeated `--support-file solver/NAME.py=PATH`
arguments expose surrounding modules to evolution. Runs may use up to four
generations.

A four-generation cube-restack trial exposed `solver/program.py` and
`solver/strategy.py`. RHO accepted the missing-import repair and explored fuller
motion sequences, but no evolved candidate completed the task. The official
CaP-X oracle completed 3/5 seeds, confirming that the task itself is feasible
but stochastic. This negative result is retained as a useful strict-gating
example rather than presented as a success.

## Measured workshop runtime

The committed notebook executions on the workshop GPU measured:

- CaP-X: 4.5 seconds for model setup, 11.4 seconds for perception/control
  setup, 14.2 seconds for one LLM call, and 11.8 seconds for one rollout.
- RHO: 4.7 seconds for model setup, 12.3 seconds for perception/control setup,
  and 109.5 seconds for HELIX. llama.cpp attributed 31.0 seconds of HELIX to
  prompt processing and token generation; candidate simulation consumed most
  of the remaining time.

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

The workshop's Gemma E2B and Gemma E4B GGUFs are baked under
`/opt/lemonade-cache`, outside the JupyterHub home-volume mount. Removing the
unused Qwen3 Coder checkpoint saves 17.3 GB. SAM2.1 Large and OWLv2 Large are
likewise baked under `/opt/capx-cache`; neither runtime path needs a Hugging Face
token or a first-run model download. Their checkpoints are staged through FP16
before an on-device FP32 conversion to avoid a multi-minute ROCm transfer while
retaining FP32 execution. Matching `*_fast.yaml` CaP-X configs retain SAM2.1
Small and OWLv2 Base for comparisons.
