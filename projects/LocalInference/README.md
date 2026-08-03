# ROSCon 2026: Local Robot Inference

Complete the notebooks in order:

1. `02_local_inference_with_lemonade.ipynb`
2. `03_robot_agents.ipynb`

The second notebook starts a headless O3DE manipulation simulation and connects
a RAI robot agent to the Lemonade model from the first notebook.

Environment checks:

```bash
/ryzers/test_ros.sh
/ryzers/test_o3de.sh
/ryzers/test_rai.sh
/ryzers/test_lemonade-sdk.sh
```

Lemonade models are cached under `~/.cache/lemonade`.
