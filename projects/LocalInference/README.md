# ROSCon 2026: Local Robot Inference

Complete the notebooks in order:

1. `02_local_inference_with_lemonade.ipynb`
2. `03_robot_agents.ipynb`
3. `04_code_as_policies_with_capx.ipynb`
4. `05_repository_as_policy_with_rho.ipynb`

The final notebook runs one bounded HELIX/OpenCode mutation against a small
CaP-X repository. It demonstrates RHO's repository-as-policy loop with the
local Gemma model; it is not a reproduction of the paper's full training run.

Environment checks:

```bash
/ryzers/test_ros.sh
/ryzers/test_o3de.sh
/ryzers/test_rai.sh
/ryzers/test_lemonade-sdk.sh
/ryzers/test_capx.sh
/ryzers/test_rho.sh
```

Lemonade models are cached under `~/.cache/lemonade`.
