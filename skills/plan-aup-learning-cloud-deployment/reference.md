# Plan an AUP Learning Cloud deployment — Reference

Sizing math, the whole-GPU evidence, the hardware-research method, the
network/topology decision table, worked examples, the BOM template, and the
interview question bank. The workflow and gates are in [SKILL.md](SKILL.md).

## Contents

- [Source guides](#source-guides)
- [Sizing model](#sizing-model)
- [Per-notebook resource config (typical)](#per-notebook-resource-config-typical)
- [Accelerator catalog and VRAM tiers](#accelerator-catalog-and-vram-tiers)
- [Researching current AMD hardware](#researching-current-amd-hardware)
- [Topology and network decision](#topology-and-network-decision)
- [Sizing procedure](#sizing-procedure)
- [Worked examples](#worked-examples)
- [BOM template](#bom-template)
- [Interview question bank](#interview-question-bank)
- [Handoff](#handoff)

## Source guides

- Overview: <https://amdresearch.github.io/aup-learning-cloud/introduction/overview.html>
- Quick Start (single-node): <https://amdresearch.github.io/aup-learning-cloud/installation/quick-start.html>
- 3-node mini-cluster (PXE diskless): <https://amdresearch.github.io/aup-learning-cloud/installation/multi-node/multi-aipc-hardware-deployment.html>
- Standard multi-node (SSH): <https://amdresearch.github.io/aup-learning-cloud/installation/multi-node.html>

Treat the live `aup-learning-cloud` repo (`runtime/values.yaml`, the spawner)
and AMD's current product pages as the sources of truth; this file condenses
the opinionated sizing path.

## Sizing model

The model is validated against industry JupyterHub capacity-planning practice.

### Concurrency, not headcount

Size on **peak concurrent users**, not total registrations — the always-on Hub
overhead is tiny and costs scale with simultaneously active users
([JupyterHub capacity planning](https://jupyterhub.readthedocs.io/en/stable/explanation/capacity-planning.html)).
Rule of thumb: peak concurrent ≈ **40-60% of total** for self-paced cohorts
([TLJH](https://tljh.jupyter.org/en/latest/howto/admin/resource-estimation.html),
[UC Berkeley CDSS](https://cdss.berkeley.edu/choosing-right-jupyterhub-infrastructure)).
Use **~100%** when a whole class is scheduled on at the same time.

### GPU dimension = machine count (whole-GPU, exclusive, no sharing)

In AUP Learning Cloud every GPU notebook claims a **whole, exclusive GPU**.
The spawner sets both the guarantee (request) and the limit to the same
integer, in
[`runtime/hub/core/spawner/kubernetes.py`](https://github.com/AMDResearch/aup-learning-cloud/blob/main/runtime/hub/core/spawner/kubernetes.py)
(around lines 740-743):

```python
if "amd.com/gpu" in requirements:
    self.extra_resource_guarantees = {"amd.com/gpu": str(requirements["amd.com/gpu"])}
    self.extra_resource_limits = {"amd.com/gpu": str(requirements["amd.com/gpu"])}
```

`amd.com/gpu` is a Kubernetes **integer extended resource** with request ==
limit, so a pod takes whole cards only. There is **no fractional / time-slicing
/ MIG / MPS sharing** in this chart (those are NVIDIA-only:
[NVIDIA time-slicing](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/25.10/gpu-sharing.html),
[MIG/MPS](https://kubedojo.com/gpu-sharing-mig-time-slicing-k8s)); the AMD ROCm
k8s device plugin allocates whole devices. This is **universal across every GPU
course** — `gpu`, `code-gpu`, `Course-CV`, `Course-DL`, `Course-LLM`, and
`Course-PhySim` all set `amd.com/gpu: "1"` in `custom.resources.requirements`
and share the same `_configure_spawner()` path; `cpu`, `code-cpu`, and `none`
request no GPU. The count is admin-configurable but only as an integer number
of whole cards.

Consequence:

```
concurrent GPU notebooks = total physical GPUs in the cluster
GPUs needed              = peak concurrent GPU users
```

- An APU AIPC (e.g. Strix Halo 8060S) = **1 iGPU = 1 concurrent GPU user**.
- A workstation/server holds **N dGPUs = N concurrent GPU users**.
- When all GPUs are busy, extra GPU spawns stay `Pending` until one frees.

### RAM/CPU dimension = per-machine spec

CPU notebooks are **best-effort** in the default chart (`cpu: "0"`,
`memory: "0Gi"`), so they pack densely and the binding constraint is **RAM**.
Standard formulas
([TLJH](https://tljh.jupyter.org/en/latest/howto/admin/resource-estimation.html),
[CDSS](https://cdss.berkeley.edu/choosing-right-jupyterhub-infrastructure)):

```
RAM per machine  = (concurrent users on that machine × max memory per user) + overhead
vCPU per machine = (concurrent users on that machine × CPU per user) + 20%
```

Note: the spawner derives a CPU limit of `cpu × 1.25` and a memory limit of
`memory × 1.5` when not explicitly set, so if you raise the per-course
`requirements` the effective ceiling is a bit higher than the request.

## Per-notebook resource config (typical)

Web-sourced typical per-user values; tune with Prometheus once running. z2jh's
default guarantee is 1G RAM, and a conservative classroom starting point is
0.5 CPU + 2GB
([z2jh user resources](https://z2jh.jupyter.org/en/stable/jupyterhub/customizing/user-resources.html)).

| Course / use | Memory per user | CPU per user | GPU | VRAM note |
| --- | --- | --- | --- | --- |
| Entry / light Python (generic `cpu`, code-server) | 2 GB (limit higher) | 0.5 vCPU | none | — |
| Computer Vision (`Course-CV`) | 8-16 GB | 1-2 vCPU | 1 whole GPU | mid VRAM ok |
| Deep Learning (`Course-DL`) | 8-16 GB | 1-2 vCPU | 1 whole GPU | needs decent VRAM; enlarge `/dev/shm` for PyTorch DataLoader |
| LLM from scratch (`Course-LLM`) | 16 GB+ | 2+ vCPU | 1 whole GPU | **large VRAM** — exclude 4GB iGPUs |
| Physics Sim / Genesis (`Course-PhySim`) | 8-16 GB | 1-2 vCPU | 1 whole GPU | mid/large VRAM |

DL frameworks try to grab most VRAM; with whole-GPU allocation that is fine
(one user per card), but it also means you cannot pack two GPU users onto one
card.

## Accelerator catalog and VRAM tiers

From `runtime/values.yaml` (`custom.accelerators`). The VRAM column is the key
chip-selection driver:

| Accelerator key | Chip | VRAM | CU | `amd.com/gpu.product-name` | Good for |
| --- | --- | --- | --- | --- | --- |
| `phx` | Radeon 780M (Phoenix iGPU) | 4 GB shared | 12 | `AMD_Radeon_780M_Graphics` | light CPU/GPU only; NOT LLM |
| `strix` | Radeon 890M (Strix iGPU) | 4 GB shared | 16 | `AMD_Radeon_890M_Graphics` | light CPU/GPU only; NOT LLM |
| `strix-halo` | Radeon 8060S (Strix Halo iGPU) | 64 GB unified | 40 | `AMD_Radeon_8060S_Graphics` | CV/DL/LLM/PhySim |
| `9070xt` | Radeon RX 9070 XT | 16 GB GDDR6 | 64 | `AMD_Radeon_RX_9070_XT` | CV/DL; mid LLM |
| `r9700` | Radeon AI PRO R9700 | 32 GB GDDR6 | 64 | `AMD_Radeon_AI_PRO_R9700` | CV/DL/LLM; multi-card workstation/server |
| `9600gre` | Radeon RX 9600 GRE | 12 GB GDDR6 | 32 | `AMD_Radeon_RX_9600_GRE` | CV/DL; light to mid LLM |

`phx` also sets `HSA_OVERRIDE_GFX_VERSION: 11.0.0`. If a fleet normalizes a
product name differently, the `nodeSelector` string must be changed to match
the real node label.

## Researching current AMD hardware

Always confirm against current AMD product pages; silicon refreshes often.

1. **Search by form factor and capability**, not tier name:
   - Ryzen AI APU mini-PCs / laptops (the AIPC, demo-like experience).
   - Radeon workstation dGPUs (e.g. AI PRO class) for single- or multi-card boxes.
   - Multi-GPU workstations / rack servers when concurrency is high.
2. **ROCm gate.** Only recommend chips with confirmed ROCm support; otherwise
   the GPU notebooks will not run.
3. **Map to a chart key.** Fit the chip to an existing accelerator key
   (`phx`/`strix`/`strix-halo`/`9070xt`/`r9700`/`9600gre`) and the expected
   `amd.com/gpu.product-name`. If it is a brand-new product with no key yet,
   tell the user it needs a `configure-aup-learning-cloud-courses` accelerator
   entry (and possibly a new image) before deployment.
4. **AIPC vs workstation vs server:** prefer many single-GPU AIPCs for small
   labs and the closest match to the demo; switch to multi-GPU chassis when the
   GPU count makes cabling/power/management of many boxes impractical.

## Topology and network decision

| Topology | When | Network needs |
| --- | --- | --- |
| **Single-node** (`./auplc-installer`) | One box; replicate the demo; ≤ a handful of users sharing one GPU sequentially | Any network; `localhost:30890` |
| **PXE-diskless cluster** | Bare AIPCs that can netboot; small teaching lab; zero per-machine install | **One flat L2 subnet**; the user's existing DHCP/router stays (dnsmasq runs Proxy-DHCP and does NOT hand out leases); service machine needs a **static/reserved IP**; Secure Boot off; netboot in firmware |
| **SSH-preinstalled cluster** | Nodes already run Ubuntu, or the network is routed/multi-subnet, or netboot is not possible | Each node reachable over SSH; tolerates multiple subnets/routers |

Networking gear rules of thumb:

- **One flat subnet** is strongly preferred for PXE-diskless (Proxy-DHCP is
  broadcast/L2-bound). Multiple routers/subnets break it unless they share a
  broadcast domain or you add DHCP relay — in that case prefer SSH-preinstalled.
- **Switch ports ≈ number of nodes + 1 uplink.** A typical consumer router has
  ~4 LAN ports; beyond that, add a managed switch (1GbE is fine for a teaching
  lab; NFS traffic benefits from 2.5/10GbE on larger clusters).
- **Static IP:** reserve one for the service/control machine (PXE/NFS/k3s
  server / API endpoint all use it). Other nodes can be DHCP.
- Keep `k3s_version` and `pxe_k3s_version` in sync (agents must not be newer
  than the server) — relevant when handing off to `deploy-aup-learning-cloud`.

### Sample IP plan (single flat subnet)

| Item | Value (example) |
| --- | --- |
| Subnet / CIDR | `192.168.1.0/24` |
| Gateway (existing router) | `192.168.1.1` |
| DHCP pool (existing) | `192.168.1.100-199` |
| Service machine (static) | `192.168.1.10` |
| Agents | DHCP from the existing pool (PXE) or static outside it (SSH) |
| Hub access | `http://192.168.1.10:30890` (NodePort) |

## Sizing procedure

1. Total users → **peak concurrent** (×0.4-0.6, or ×1.0 for a scheduled class).
2. Split peak into **GPU sessions** and **CPU-only sessions**.
3. **GPU count = peak concurrent GPU users.** Convert to machines by chassis:
   AIPC = 1 GPU/box; workstation/server = N GPUs/box.
4. **RAM check** each machine against the CPU/GPU sessions it will host using
   the RAM formula; bump per-machine memory or add a box if short.
5. **Chip tier** from per-course VRAM needs (LLM → 64GB Strix Halo or 32GB
   R9700; light → smaller is fine).
6. **+1 control/service node** (or co-locate on a GPU node for a tiny lab, with
   a stated SPOF caveat).
7. **Research current models** that satisfy 3-5 and are ROCm-supported; produce
   the BOM.

## Worked examples

### Example A — 30 students, LLM course, one scheduled class slot

- Concurrency: whole class on together → peak ≈ **30**, all GPU, all need large
  VRAM.
- GPUs needed = 30. LLM ⇒ Strix Halo (64GB) or R9700 (32GB).
- **Option 1 (AIPC):** 30× Strix Halo AIPC (1 GPU each) + 1 control node ≈
  **31 machines**, one flat subnet, a 48-port switch.
- **Option 2 (dense):** workstations/servers with 4× R9700 each → ~8 GPU boxes +
  1 control node ≈ **9 machines**; fewer boxes to cable/power/manage, higher
  per-box cost.
- Present both; let the user trade box count vs per-box cost.

### Example B — 60 students, mixed CV/DL, self-paced

- Concurrency ≈ 50% → peak ≈ **30** active; assume ~20 GPU + ~10 CPU at peak.
- GPUs needed = 20 (CV/DL ⇒ 16-32GB VRAM ok: 9070xt/R9700, or Strix Halo).
- CPU-only 10 sessions pack onto a few nodes; RAM = 10 × ~4GB + overhead ≈ a
  single 64GB node handles them, or fold onto GPU nodes.
- ~20 GPU boxes (AIPC) **or** ~5 boxes × 4 cards + 1 control node.

### Example C — small demo replica

- 1 box, sequential single-GPU use. Use **single-node** `./auplc-installer` on
  one Strix Halo AIPC. No switch/router changes. Hand off to
  `install-aup-learning-cloud-single-node`.

## BOM template

```
AUP Learning Cloud — recommended bill of materials

Requirements assumed:
  Courses           : <e.g. LLM, DL>
  Total students    : <N>     Peak concurrent: <M>   (assumption: <ratio/scheduled>)
  Peak GPU sessions : <G>     Peak CPU sessions: <C>

Compute:
  <qty> × <AMD machine model>  (<chip>, <VRAM>, <GPUs/box>)   → <total GPUs>
  1 × control/service node     (<model or "co-located">)

Networking:
  1 × <managed switch, port count>           (≈ nodes + uplink)
  reuse existing router/DHCP; reserve 1 static IP for the service node
  <cabling>

Topology : <single-node | PXE-diskless | SSH-preinstalled>
Storage  : <local-path (single box) | NFS on service node | dedicated NFS>

Notes / assumptions:
  - GPU is whole-card per user (no sharing): concurrent GPU users = total GPUs.
  - <SPOF / backup caveats>
Next step : <install-aup-learning-cloud-single-node | deploy-aup-learning-cloud>
```

## Interview question bank

Requirements:

- Which courses/toolkits (CV / DL / LLM / PhySim / generic)?
- Total students; one scheduled class at a time, or self-paced?
- Best guess at peak concurrent users; how many of those need a GPU?
- Do notebooks need to persist across reboots? Rough per-user disk?
- Budget band? Internet access or air-gapped?

Network:

- How many routers? How many subnets/CIDRs and what IP ranges?
- Static IP available for one machine, or DHCP only?
- Managed switch? How many free ports?
- Can the machines network-boot (PXE), or will each get an OS install?
- Any VLANs/firewalls between the machines?

## Handoff

| After the plan is agreed | Use skill |
| --- | --- |
| Install on one box / demo replica | `install-aup-learning-cloud-single-node` |
| Build the multi-node cluster (PXE or SSH) | `deploy-aup-learning-cloud` |
| Enable the chosen courses / add an accelerator entry for a new chip | `configure-aup-learning-cloud-courses` |
| Build/publish custom course images | `build-aup-learning-cloud-images` |

## Out of scope

Running any install/deploy command, buying hardware, production HA/TLS/ingress
hardening, monitoring, and authoring images or course catalogs — this skill
stops at the recommendation/BOM and hands off.
