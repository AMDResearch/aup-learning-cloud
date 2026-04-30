# Overview

AUP Learning Cloud is a JupyterHub-based learning platform for curated course environments, custom repositories, and shared GPU-enabled workspaces on Kubernetes.

```{image} ../_static/images/software-stack.png
:alt: Software Architecture
:align: center
```

## What It Provides

### Resource Selection At Spawn Time

Users do not launch into a single fixed notebook image. The platform presents a resource picker that can expose:

- course environments such as CV, DL, LLM, and PhySim
- generic CPU or GPU environments
- accelerator-specific options defined by the deployment
- optional Git repository cloning on startup

What each user can see is controlled by JupyterHub group membership and `custom.teams.mapping`.

### Multiple Authentication Modes

The Hub currently supports four authentication modes:

- `auto-login`
- `dummy`
- `github`
- `multi`

`multi` combines GitHub OAuth and native local accounts on one login page. In GitHub-backed deployments, GitHub team membership can be synchronized into JupyterHub groups and used for resource access control.

### Admin Console

The built-in admin console at `/hub/admin` includes:

- a **Users** view for creating users, resetting passwords, managing quotas, and starting or stopping servers
- a **Groups** view for reviewing group membership and group-to-resource mappings
- a **Dashboard** view for usage analytics, active sessions, pending spawns, and resource distribution

### Quota And Usage Tracking

When quota is enabled, the platform tracks usage sessions, enforces minimum balance before spawn, supports unlimited users, and can apply scheduled refresh rules with Kubernetes CronJobs.

### Monitoring And Metrics

The chart can expose Hub metrics to Prometheus and optionally install ServiceMonitor, PrometheusRule, and Grafana dashboard resources.

## Deployment Modes

### Single-Node

The primary workstation/developer flow uses `./auplc-installer` to install K3s, prepare runtime values, and deploy the Hub.

The checked-in default values in this repository currently describe a local deployment with:

- NodePort access on `30890`
- `local-path` storage
- ingress disabled
- prePuller disabled

### Multi-Node

Cluster deployments use the Ansible playbooks in `deploy/ansible/` plus Helm deployment with `runtime/values-multi-nodes.yaml.example` as the starting point.

NFS storage, ingress, TLS, and other production-oriented components are deployment choices, not mandatory defaults.

## Learning Solutions

AUP Learning Cloud currently ships the following learning toolkits:

- **Computer Vision**
- **Deep Learning**
- **Large Language Models**
- **Physics Simulation**

## Acknowledgment

AUP would like to thank the following universities and professors. This learning solution was made possible through the joint efforts of these partners.

| University | Professors and Labs | Toolkits |
|---|---|---|
| National Taiwan University | [Prof. Chun-Yi Lee](https://www.csie.ntu.edu.tw/en/member/Faculty/Chun-Yi-Lee-67240464), [ELSA Lab](https://elsalab.ai/) | DL, CV |
| Nanjing University | [Prof. Jingwei Xu](https://njudeepengine.github.io/jingweixu/), [NJUDeepEngine](https://github.com/NJUDeepEngine) | LLM |

The following repositories and icons are used in AUP Learning Cloud, either in close to original form or as an inspiration:

- [Genesis](https://github.com/Genesis-Embodied-AI/Genesis)
- [Flaticon](https://www.flaticon.com): deployment (Prashanth Rapolu 15, Freepik), team and user (Freepik), machine learning (Becris)
