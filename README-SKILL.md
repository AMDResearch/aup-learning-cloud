# AUP Learning Cloud Skills (`auplc-skills`)

Agent Skills that help any coding agent deploy and maintain
[AUP Learning Cloud](https://github.com/AMDResearch/aup-learning-cloud) — the
multi-node JupyterHub-on-k3s teaching platform for AMD GPUs.

Skills follow the standardized [Agent Skills](https://github.com/anthropics/skills)
format and interoperate with the major coding agents: Cursor, Claude Code,
OpenAI Codex, and Gemini CLI.

> **Tech preview.** The catalog spans install → deploy → configure → build →
> upgrade → troubleshoot. Expect frequent changes while the foundations settle;
> the skills are a first draft to review with the operators who own each area.

## The catalog

The skills are organized into three groups so an agent can start in the right
place for a task. It is still **one bundled plugin** — installing it brings
every skill at once; the groups are a routing aid (each skill's `description`
also carries its `Group:` tag). See
[plugin-docs/skill-categories.md](plugin-docs/skill-categories.md) for the full taxonomy and
routing guidance.

### Plan and deploy AUP Learning Cloud

Bring the platform into existence: size it, install or deploy it, and build its
images.

| Skill | What it does | Status |
| --- | --- | --- |
| [`plan-aup-learning-cloud-deployment`](skills/plan-aup-learning-cloud-deployment/SKILL.md) | Size a new deployment for a prospective adopter: interview course/headcount needs and the network, research current AMD silicon, then recommend how many AIPCs/workstations/servers and routers/switches to buy, the topology, an IP plan, and a buyer-facing bill of materials. | in-repo |
| [`install-aup-learning-cloud-single-node`](skills/install-aup-learning-cloud-single-node/SKILL.md) | Install on a single AMD GPU/APU box with the `./auplc-installer` flow: prerequisites, GPU/courses/image flags, gated install, verify at `localhost:30890`. | in-repo |
| [`deploy-aup-learning-cloud`](skills/deploy-aup-learning-cloud/SKILL.md) | Deploy end to end on a multi-AIPC PXE-diskless or SSH-preinstalled k3s cluster: interview the operator, generate the Ansible inventory + PXE vars + Helm values (helper scripts), then drive the install with confirmation gates at risky steps. | in-repo |
| [`build-aup-learning-cloud-images`](skills/build-aup-learning-cloud-images/SKILL.md) | Build and publish the Hub and notebook/course Docker images with `img build`, incl. GPU-target tagging and registry push. | in-repo |

### Maintain AUP Learning Cloud

Operate and keep a running deployment healthy: upgrade, debug, observe, secure
logins, manage users, and control network/storage exposure.

| Skill | What it does | Status |
| --- | --- | --- |
| [`upgrade-aup-learning-cloud`](skills/upgrade-aup-learning-cloud/SKILL.md) | Upgrade the JupyterHub chart/values/images and the k3s cluster on a running deployment, in a safe order with rollback. | in-repo |
| [`troubleshoot-aup-learning-cloud`](skills/troubleshoot-aup-learning-cloud/SKILL.md) | Diagnose netboot, node-join, GPU scheduling, storage, and auth failures from runtime evidence, then hand off the fix. | in-repo |
| [`monitor-aup-learning-cloud`](skills/monitor-aup-learning-cloud/SKILL.md) | Wire the Hub into Prometheus + Grafana: ServiceMonitor, authenticated metrics, dashboards, alert rules, and the metrics NetworkPolicy. | in-repo |
| [`configure-aup-learning-cloud-auth`](skills/configure-aup-learning-cloud-auth/SKILL.md) | Configure auto-login, dummy, native, GitHub, or native plus GitHub providers, along with GitHub team sync and first-run admin bootstrap. | in-repo |
| [`manage-aup-learning-cloud-users`](skills/manage-aup-learning-cloud-users/SKILL.md) | Day-2 user/group/quota operations via the admin console and `manage_users.py`: bulk onboarding, passwords, admins, and quota grants/refresh. | in-repo |
| [`expose-aup-learning-cloud`](skills/expose-aup-learning-cloud/SKILL.md) | Take a deployment past the local defaults: NodePort/LoadBalancer/ingress + TLS, CORS origins, externally-terminated TLS, and shared NFS storage. | in-repo |

### Course and other editor

Edit what lives inside the platform: the course catalog, new course content, and
per-user repository cloning.

| Skill | What it does | Status |
| --- | --- | --- |
| [`configure-aup-learning-cloud-courses`](skills/configure-aup-learning-cloud-courses/SKILL.md) | Edit the course catalog, spawn-UI metadata, GPU accelerator selectors, team mappings, and quota in `values.yaml`, then re-apply. | in-repo |
| [`develop-aup-learning-cloud-courses`](skills/develop-aup-learning-cloud-courses/SKILL.md) | Author a new course end to end: notebooks under `projects/`, a course image, and catalog registration, then build + wire it in. | in-repo |
| [`configure-aup-learning-cloud-repos`](skills/configure-aup-learning-cloud-repos/SKILL.md) | Configure per-user Git repo cloning: the spawn-form repo field/picker, private-repo tokens, provider allowlist, and clone persistence. | in-repo |

## What is a skill?

A skill is a self-contained folder that bundles everything an agent needs to
perform a focused task: instructions, helper scripts, and references. At its
core is a `SKILL.md` file with YAML frontmatter — a `name` and a short
`description` that tells the agent *when* the skill should activate — followed
by the guidance the agent reads while the skill is in use.

```
skills/
  deploy-aup-learning-cloud/
    SKILL.md          # routing frontmatter + workflow
    skill-card.md     # governance card (Description, Owner)
    reference.md      # full step-by-step commands + troubleshooting
    scripts/          # executable helpers
```

When an agent decides a skill is relevant (or you invoke it explicitly), it
loads `SKILL.md` and follows the instructions inside. Descriptions stay in
context cheaply; the full body loads only when the task actually matches.

## Installation

The whole catalog ships as a single bundled plugin (`auplc`), so any of the
methods below installs every skill at once. Pick the one that matches your
agent.

### Claude Code

Install with the [plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces):

```
/plugin marketplace add AMDResearch/aup-learning-cloud
/plugin install auplc@auplc-skills
```

### Cursor

Install from the Cursor Marketplace, or add manually via **Settings → Rules →
Add Rule → Remote Rule (Github)** with `AMDResearch/aup-learning-cloud`. Cursor scans
the repo and copies the skills into `.cursor/skills/`.

### npx skills

Install with the [`npx skills`](https://skills.sh) CLI (works with any agent
that follows the Agent Skills standard):

```
npx skills add https://github.com/AMDResearch/aup-learning-cloud
```

### Clone / Copy

Clone this repo and copy (or symlink) the skill folders you want from `skills/`
into your agent's skills directory. Each agent discovers `SKILL.md`
automatically.

```bash
git clone https://github.com/AMDResearch/aup-learning-cloud.git
cp -r aup-learning-cloud/skills/deploy-aup-learning-cloud <agent-skills-dir>/
```

| Agent | Skills directory (personal / project) |
| --- | --- |
| Cursor | `~/.cursor/skills/` / `.cursor/skills/` |
| Claude Code | `~/.claude/skills/` / `.claude/skills/` |
| Codex | `$HOME/.agents/skills` / `$REPO_ROOT/.agents/skills` |

## Recommended models

These skills drive long, gated workflows — Ansible runs, `kubectl`/`helm`
rollouts, netboot setup — where the agent has to hold a plan across many phases
and stop at each confirmation gate. They work best on a frontier reasoning model
with the reasoning effort turned up.

| Agent | Model | Reasoning effort |
| --- | --- | --- |
| Claude Code | Opus 4.8 | high |
| Codex | GPT-5.6-Sol | high |
| OpenCode | DeepSeek V4 Flash | high |

Any agent that follows the Agent Skills standard can load the catalog. If yours
isn't listed, pick its strongest reasoning model and raise the effort/thinking
setting to high.

## Using a skill

Once installed, reference it in plain language while talking to your agent. In
most cases the agent picks the right skill on its own from the description.

### Example prompts — the three ways to stand up a deployment

There are three deployment paths. Pick the prompt that matches your hardware;
the agent routes to the right skill and interviews you for the rest.

- **Single node** (one AMD GPU/APU box → `install-aup-learning-cloud-single-node`):

  > *"Install AUP Learning Cloud on this single AMD GPU workstation with the
  > `./auplc-installer` flow and verify it at `localhost:30890`."*

- **Multi-node, PXE diskless netboot** (one service machine netboots diskless
  agents → `deploy-aup-learning-cloud`, `topology: pxe-diskless`):

  > *"Deploy AUP Learning Cloud across my 3 AIPCs over PXE — the machine I'm on
  > right now is the head/service node, and the other two are diskless agents
  > that should netboot and auto-join k3s."*

- **Multi-node, SSH pre-installed** (every node already runs Ubuntu, reachable
  over SSH → `deploy-aup-learning-cloud`, `topology: ssh-preinstalled`):

  > *"Deploy AUP Learning Cloud on my 4 nodes that already run Ubuntu 24.04 and
  > are reachable over SSH — the machine I'm on right now is the head/server
  > node, install k3s and ROCm on all of them with Ansible, no PXE."*

The two multi-node prompts both drive `deploy-aup-learning-cloud`; its Phase 1a
gate asks you to confirm the topology (`pxe-diskless` vs `ssh-preinstalled`)
before touching any machine.

> **Tip — watch every command live in your own tmux.** These deploy/install
> skills run a lot of shell commands (Ansible, `kubectl`, `helm`, netboot
> setup). To see exactly what an agent runs, have it drive a tmux session you
> keep open instead of its hidden shell. First, open the session:
>
> ```bash
> tmux new -s auplc
> ```
>
> Then tell the agent to send commands to it, e.g.:
>
> > *"Run every shell command by sending it to my tmux session `auplc` with
> > `tmux send-keys -t auplc '<command>' Enter`, then read the pane with
> > `tmux capture-pane -t auplc -p` to check the result — don't use your own
> > shell."*
>
> You watch the commands and their output scroll in the `auplc` pane in real
> time, and can hit `Ctrl-C` there to stop anything that looks wrong. This works
> in any agent that has terminal access (Claude Code, Cursor, Codex).

## Repository layout

```
skills/                  # All skills the agent can load
templates/skill-template # Starting point for a new skill
plugin-docs/             # Plugin authoring + governance docs
.claude-plugin/          # Claude marketplace + bundled-plugin manifest (hand-maintained)
.cursor-plugin/          # Cursor marketplace + plugin manifest (generated)
plugin-metadata.json     # Vendor-neutral identity/discovery metadata
.github/scripts/         # Validation + publish scripts
.github/workflows/       # CI that validates skills and manifests
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for authoring conventions and
[plugin-docs/adding-a-skill.md](plugin-docs/adding-a-skill.md) for the step-by-step procedure
to add a new skill. Run the same checks CI runs before opening a PR:

```bash
./.github/scripts/check.sh
```
