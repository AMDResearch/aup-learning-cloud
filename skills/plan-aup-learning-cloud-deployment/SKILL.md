---
name: plan-aup-learning-cloud-deployment
description: >-
  Group: Plan & deploy AUP Learning Cloud. Recommends the hardware sizing,
  cluster topology, network plan, and a
  buyer-facing bill of materials (BOM) for someone who saw an AUP Learning
  Cloud / AUPLC demo and wants to stand up their own local deployment. Use
  when the user asks how many AIPCs / machines / GPUs / routers they need,
  wants sizing or a hardware recommendation, says "I saw the demo and want to
  deploy this myself", "what should I buy", "bill of materials", "spec out a
  lab", or describes a class headcount and a network (routers, subnets, static
  IP vs DHCP) and wants a configuration. It interviews requirements + network,
  researches current AMD silicon, and sizes the cluster. Do not use to actually
  run the install (install-aup-learning-cloud-single-node), build a multi-node
  cluster (deploy-aup-learning-cloud), or edit the course catalog
  (configure-aup-learning-cloud-courses) — hand off to those once the plan is
  agreed.
---

# Plan an AUP Learning Cloud deployment

Turn a prospective adopter's needs into a concrete recommendation: how many
AMD machines (Ryzen AI AIPC, Radeon workstation, or server) and how much
networking gear to buy, which chips to pick, what cluster topology to use, and
an IP/network plan — ending in a sizing table and a buyer-facing bill of
materials (BOM). This is the pre-purchase advisory step that precedes the
install/deploy skills.

The single measurable outcome: a defensible BOM + sizing/topology/network plan
the user can act on. Full sizing math, the hardware-research method, the
network decision table, worked examples, and the BOM template are in
**[reference.md](reference.md)**.

## Prerequisites

- Web access (to look up the latest AMD silicon and confirm ROCm support).
- No cluster or checkout is required — this skill produces a plan, not a
  running system.
- Helpful context: the AUP Learning Cloud
  [overview](https://amdresearch.github.io/aup-learning-cloud/introduction/overview.html)
  and [quick start](https://amdresearch.github.io/aup-learning-cloud/installation/quick-start.html).

## Phase 1 — Interview the requirements

Ask, and confirm back, before sizing anything:

1. **Courses/toolkits** wanted: Computer Vision, Deep Learning, LLM-from-scratch,
   Physics Sim, and/or generic CPU/GPU + code-server. This drives both the GPU
   VRAM tier and which images to enable later.
2. **Total headcount** and the **session pattern**: a whole class on at the same
   time (scheduled lab) vs self-paced/錯峰 usage.
3. **Peak concurrent users**, split into **GPU sessions vs CPU-only sessions**.
   If the user only knows the total, estimate peak (see reference) and confirm.
4. **Persistence/storage** expectations (do notebooks need to survive reboots;
   rough per-user disk).
5. **Budget band** and **online vs air-gapped**.

## Phase 2 — Interview the network environment

1. How many **routers**, and how many **subnets / CIDRs** with which IP ranges.
2. **Static IP vs DHCP**; can a stable/reserved IP be given to one machine.
3. A **managed switch** and how many **free ports** (PoE not needed).
4. **Internet access** from the would-be service machine; any VLANs/firewalls.
5. Whether the machines are **bare (can netboot)** or will each get an OS.

## Phase 3 — Research current AMD hardware

Do not rely on memory — **web-search the latest AMD silicon** and match it to
the requirements:

1. Search current AMD options across form factors: **Ryzen AI APUs** (mini-PC /
   laptop AIPC), **Radeon workstation dGPUs**, and **multi-GPU workstations or
   servers**. Compare by **compute (CU/TFLOPs) and VRAM**, not marketing tier.
2. **Gate every candidate on ROCm support** — if a chip is not ROCm-supported it
   cannot run the GPU notebooks.
3. **Map the chip to a chart accelerator key** (`phx`, `strix`, `strix-halo`,
   `9070xt`, `r9700`, or the generic `rdna4`) and the expected
   `amd.com/gpu.product-name` node label. A brand-new chip with no existing key
   is a flag to raise with the user.
4. Prefer **multi-GPU chassis** (workstation/server) when peak concurrent GPU
   users is high enough that many single-GPU AIPCs become impractical to cable,
   power, and manage. Keep AIPCs for small labs and the demo-like experience.

## Phase 4 — Size the cluster

The full formulas and per-notebook config table are in
[reference.md](reference.md). The shape of it:

1. **Concurrency, not headcount.** Convert total users to **peak concurrent**
   (~40-60% of total for self-paced; ~100% for a whole-class scheduled lab).
2. **GPU drives machine count (whole-GPU, no sharing).** Each GPU notebook in
   AUPLC claims a **whole, exclusive** `amd.com/gpu: "1"` (request == limit);
   there is no time-slicing/MIG, and this is the same for every GPU course. So
   `GPUs needed = peak concurrent GPU users`. An APU box = 1 GPU; a
   workstation/server = N cards.
3. **RAM/CPU sets the per-machine spec.** CPU notebooks are best-effort and pack
   densely (RAM-bound): `RAM ≈ (concurrent users on the node × max mem/user) +
   overhead`. Pick per-user memory from the course type (reference table).
4. **VRAM picks the chip tier.** Exclude 4GB iGPUs (780M/890M) for LLM/large
   models; steer to Strix Halo (64GB) or R9700 (32GB) for those.
5. **Add a control/service node.** PXE/NFS/k3s-server overhead; small labs may
   co-locate it on a GPU node (state the single-point-of-failure trade-off).

## Phase 5 — Plan topology and network

1. **Choose the topology** (decision table in reference):
   - **Single-node** (`./auplc-installer`) for one box / demo replica.
   - **PXE-diskless cluster** for bare AIPCs on **one flat L2 subnet** that can
     netboot (relies on the user's existing DHCP/router; the service machine
     needs a static IP).
   - **SSH-preinstalled cluster** when nodes already have an OS or the network is
     routed/multi-subnet.
2. Derive the **switch-port count** (≈ nodes + uplink) and whether the existing
   router(s) suffice or a managed switch is needed.
3. Produce an **IP plan**: the static service-machine IP, the node subnet/CIDR,
   gateway, and DNS — consistent with the topology you chose.

## Phase 6 — Deliver the recommendation

Produce, for the user:

- A **sizing table** (peak concurrency → GPU count → machine count + the chosen
  chip/VRAM, with the assumptions spelled out).
- A **topology choice** and an **IP/network plan**.
- A **bill of materials**: machine model + quantity + GPU, plus switch/router and
  cabling, framed so the user can purchase (this is what leads to AMD hardware
  sales). Offer at least an AIPC-based option and a denser workstation/server
  option when concurrency is non-trivial.
- A **handoff**: point to `install-aup-learning-cloud-single-node` (one box) or
  `deploy-aup-learning-cloud` (cluster) to execute, and
  `configure-aup-learning-cloud-courses` to enable the chosen courses.

## Safety

- **Advisory only.** This skill plans; it does not install, buy, or change any
  system. Never run installer/deploy commands from here.
- **State every assumption** (concurrency ratio, per-user memory, GPUs per
  chassis) so the user can correct them before spending money.
- **Always confirm ROCm support** for any recommended silicon; never recommend a
  chip you could not verify is supported.
- **Flag single-point-of-failure** trade-offs of all-in-one small labs, and
  storage durability (local-path/NFS-on-one-box is disposable without backups).

## Reference

Sizing formulas + per-notebook config table, the whole-GPU evidence, the
hardware-research method, the network/topology decision table, worked examples,
the BOM template, and the interview question bank: [reference.md](reference.md).
