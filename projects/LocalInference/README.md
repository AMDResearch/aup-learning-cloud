# ROSCon 2026: Local Robot Inference

Complete the notebooks in order:

0. `0_overview.ipynb`
1. `1_local_inference.ipynb`
2. `2_robot_agents.ipynb`
3. `3_code_as_policy.ipynb`
4. `4_robot_harness_optimization.ipynb`
5. `temp_evolving_rai.ipynb`

Notebook 4 begins with a workshop-sized, one-generation repair of an authentic
cube-stack program using Gemma E2B. It then loads measured results from a longer
two-generation HELIX/OpenCode evolution over equal cube-stack and spill-wipe
targets. Qwen3-Coder proposes repository mutations, HELIX retains per-task
winners on an instance frontier, and generation 2 may select or merge frontier
parents. The notebook stops at the recorded train/validation evidence; run
`scripts/rho_multitask_study.py` separately to repeat the longer experiment.

## Recorded study evidence

`recorded_results/overnight_study_summary.json` is the compact entry point for
the controlled overnight study. It links to:

- `capx_matrix_analysis.json`: 60 same-image model rollouts, the 4-task oracle,
  task metrics, latency, code signals, and failure taxonomy.
- `rho_study_analysis.json`: three single-policy mutation-agent preflights,
  Qwen surface comparisons, the two-generation multi-task result, and the
  bounded cube-restack depth study.
- `video_validation.json`: recording counts, report-path checks, container
  validation, and ffprobe results.
- `capx_selected/provenance.json`: selected local Gemma programs and their
  exact source trials.

The raw per-trial CaP-X and RHO reports remain below `recorded_results/`.
Regenerate the compact analyses after adding new shards with:

```bash
python scripts/capx_analyze.py \
  recorded_results/capx_primary_oracle/results.json \
  recorded_results/capx_primary_qwen/results.json \
  recorded_results/capx_local_gemma_shards/*/results.json \
  --output recorded_results/capx_matrix_analysis.json
python scripts/rho_analyze.py \
  --recorded-root recorded_results \
  --capx-analysis recorded_results/capx_matrix_analysis.json \
  --output recorded_results/rho_study_analysis.json
```

The temporary Evolving RAI notebook applies the same one-generation
repository-evolution pattern to a live RAI tool-calling agent. A deterministic
in-memory tabletop replaces the full O3DE benchmark so it fits the workshop:
HELIX edits both `prompt.py` and `tools.py`, the notebook displays the selected
files, and RAI reruns one held-out manipulation test. It does not replay or
claim to reproduce paper results.

## Measured workshop runtime

Measured on the workshop Strix Halo GPU:

- CaP-X: 4.5 seconds for model setup, 11.4 seconds for perception/control
  setup, 14.2 seconds for one LLM call, and 11.8 seconds for one rollout.
- RHO Part A: allow about 4–8 minutes for model/service setup, four simulator
  evaluations, and one bounded OpenCode mutation.
- RHO Part B: the notebook loads compact pre-rendered evidence immediately.
  It shows only the train/validation scores already produced by HELIX. The
  longer two-generation experiment remains available as
  `scripts/rho_multitask_study.py` rather than running additional evaluation
  suites in the notebook.

Environment checks:

```bash
/ryzers/test_ros.sh
/ryzers/test_o3de.sh
/ryzers/test_rai.sh
/ryzers/test_lemonade-sdk.sh
/ryzers/test_capx.sh
/ryzers/test_rho.sh
/ryzers/test_rho_multitask.sh
/ryzers/test_rai_toy_evolution.sh
```

The toy RAI evolution test is static/mock by default. Inside the
LocalInference image, opt into a real RAI seed-versus-repaired agent check:

```bash
RAI_TOY_RUN_LIVE=1 /ryzers/test_rai_toy_evolution.sh
```

The workshop's Gemma E2B, Gemma E4B, and Qwen3-Coder Q4_K_M GGUFs are baked
under `/opt/lemonade-cache`, outside the JupyterHub home-volume mount. Notebook
4 uses Gemma E2B for the fast live mutation and the 17.3 GB Qwen checkpoint for
the recorded multi-task evolution. SAM2.1 Large and OWLv2 Large are likewise
baked under `/opt/capx-cache`; neither runtime path needs a Hugging Face token
or a first-run model download. Their checkpoints are staged through FP16 before
an on-device FP32 conversion to avoid a multi-minute ROCm transfer while
retaining FP32 execution. Matching `*_fast.yaml` CaP-X configs retain SAM2.1
Small and OWLv2 Base for comparisons.
