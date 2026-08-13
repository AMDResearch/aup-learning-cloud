# Skill categories

The catalog is one bundled plugin, but its skills are organized into three
groups so an agent (or a person) can start in the right place for a task. The
grouping is a routing aid, not a packaging boundary: installing the plugin
brings every skill, and each skill's `SKILL.md` `description` begins with a
`Group:` tag so the category travels with the routing signal the agent loads.

When you get a task, identify the group first, then pick the skill within it.

## Plan and deploy AUP Learning Cloud

Bring the platform into existence: size it, install or deploy it, and build the
images it runs. Reach for this group when nothing is running yet (or you are
adding/replacing infrastructure) and the goal is to stand the platform up.

- `plan-aup-learning-cloud-deployment` — pre-purchase sizing, topology, network
  plan, and bill of materials.
- `install-aup-learning-cloud-single-node` — single-box `./auplc-installer`
  install.
- `deploy-aup-learning-cloud` — multi-node PXE / SSH + Ansible + Helm cluster
  deploy.
- `build-aup-learning-cloud-images` — build/publish the Hub and notebook/course
  images.

Tag: `Group: Plan & deploy AUP Learning Cloud.`

## Maintain AUP Learning Cloud

Operate and keep a running deployment healthy. Reach for this group when the
platform already exists and the goal is day-2 operations: upgrades, debugging,
observability, login security, user/quota administration, and how the Hub is
exposed and stored.

- `upgrade-aup-learning-cloud` — chart/values/image and k3s upgrades with
  rollback.
- `troubleshoot-aup-learning-cloud` — evidence-first diagnosis of a broken
  deployment.
- `monitor-aup-learning-cloud` — Prometheus/Grafana, ServiceMonitor, alerts.
- `configure-aup-learning-cloud-auth` — auth mode, GitHub App/OAuth, team sync,
  native accounts, admin bootstrap.
- `manage-aup-learning-cloud-users` — users/groups/quota operations and class
  onboarding.
- `expose-aup-learning-cloud` — NodePort/LoadBalancer/ingress + TLS, CORS, and
  NFS storage.

Tag: `Group: Maintain AUP Learning Cloud.`

## Course and other editor

Edit what lives inside the platform. Reach for this group when the cluster is
fine and the goal is content: the spawnable course catalog, authoring new course
material, or the per-user repositories learners pull into their workspaces.

- `configure-aup-learning-cloud-courses` — edit the course catalog, spawn-UI
  metadata, accelerators, team mapping, and quota knobs in `values.yaml`.
- `develop-aup-learning-cloud-courses` — author a new course end to end
  (notebooks → image → catalog registration).
- `configure-aup-learning-cloud-repos` — per-user Git repo cloning (spawn-form
  field/picker, private-repo tokens, persistence).

Tag: `Group: Course & other editor.`

## Cross-group handoffs

Tasks often cross a boundary; hand off rather than stretch a skill:

- Sizing/planning (plan) hands off to install or deploy once a plan is agreed.
- Authoring a course (develop, editor group) hands off to
  `build-aup-learning-cloud-images` (deploy group) to build the image, then to
  `configure-aup-learning-cloud-courses` (editor group) to wire it in.
- `troubleshoot` (maintain) diagnoses, then hands the fix to the matching
  deploy/install/configure/upgrade skill.

## Adding a new skill

Assign exactly one group, prepend the group's `Group:` tag to the new skill's
`description`, add its row under that group's table in the
[skills README](../README-SKILL.md), and list it here. See
[adding-a-skill.md](adding-a-skill.md) for the full procedure.
