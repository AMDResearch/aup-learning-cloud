---
name: monitor-aup-learning-cloud
description: >-
  Group: Maintain AUP Learning Cloud. Wires AUP Learning Cloud into a
  Prometheus + Grafana monitoring stack: enables
  the chart's monitoring resources (ServiceMonitor, authenticated metrics token,
  Grafana dashboard ConfigMaps, PrometheusRule alerts, and the metrics
  NetworkPolicy) and connects them to kube-prometheus-stack or an existing
  Prometheus Operator. Use when the user wants to monitor the Hub, scrape
  /hub/metrics, set up Prometheus/Grafana/alerts, install kube-prometheus-stack,
  enable a ServiceMonitor, see the AUP Hub Grafana dashboards, or debug a hub
  target that is DOWN / Unauthorized / not scraped. Triggers include
  monitoring.enabled, serviceMonitor, releaseLabel, hubMetrics,
  allowUnauthenticatedScrape, prometheusRule, grafana.dashboard,
  kube-prometheus-stack, hub-metrics, hub_spawn_failed_total,
  hub-metrics-token. Do not use to install/deploy the platform itself
  (install-/deploy-aup-learning-cloud) or to edit courses/quota
  (configure-aup-learning-cloud-courses).
---

# Monitor AUP Learning Cloud

Turn on Hub observability: have the chart create the monitoring objects
(`ServiceMonitor`, authenticated token secret, Grafana dashboard ConfigMaps,
alert rules, metrics `NetworkPolicy`) and make a Prometheus Operator stack
scrape `/hub/metrics` so dashboards and alerts light up.

Enable the `monitoring.*` block in a values overlay and re-apply with Helm. The
full value reference, the kube-prometheus-stack install, and troubleshooting are
in **[reference.md](reference.md)**.

## Prerequisites

- A running (or about-to-deploy) AUP Learning Cloud, plus `helm` + `kubectl`.
- Either install `kube-prometheus-stack` (reference) **or** an existing
  Prometheus Operator + Grafana you can point at the `jupyterhub` namespace.
- Know the Prometheus Operator's selector label — the chart stamps `release:
  <monitoring.releaseLabel>` on `ServiceMonitor`/`PrometheusRule`, and it must
  match what the operator selects.

## Decide the integration

| Situation | Action |
| --- | --- |
| No monitoring stack yet | Install `kube-prometheus-stack` as release `monitoring` in namespace `monitoring`; keep `releaseLabel: monitoring` |
| Existing Prometheus Operator + Grafana | Set `monitoring.releaseLabel` to the operator's selector; confirm it watches `monitoring` ns and can scrape `jupyterhub` |

## Workflow

1. **Ensure a stack exists.** Confirm Prometheus Operator + Grafana are running
   (install kube-prometheus-stack if not — see reference).
2. **Enable monitoring values** in the overlay. Recommended production shape:

   ```yaml
   monitoring:
     enabled: true
     namespace: monitoring
     releaseLabel: monitoring
     hubMetrics:
       enabled: true
       allowUnauthenticatedScrape: false
     serviceMonitor:
       enabled: true
       interval: 15s
       authorization:
         enabled: true
         type: Bearer
         hubServiceName: prometheus-metrics
         secret: { create: true, name: "", key: token }
     grafana:
       dashboard: { enabled: true }
     prometheusRule:
       enabled: true
   ```

3. **Keep `releaseLabel` honest.** It must equal the operator's rule/monitor
   selector or nothing gets scraped.
4. **Pre-flight the render.** `helm template jupyterhub ./runtime/chart -f
   runtime/values.yaml -f <overlay>` must succeed (the chart validates that
   `hubServiceName` exists under `hub.services` with a matching `read:metrics`
   role).
5. **Apply.**

   ```bash
   helm upgrade --install jupyterhub ./runtime/chart -n jupyterhub \
     -f runtime/values.yaml -f <overlay>
   ```

6. **Verify** the objects and the live target:

   ```bash
   skills/monitor-aup-learning-cloud/scripts/verify_monitoring.sh
   ```

   It checks the `ServiceMonitor`, token secret, dashboard ConfigMap, and
   metrics `NetworkPolicy`, then port-forwards Prometheus and confirms the
   `hub` target is `UP`. Manual checks are in [reference.md](reference.md).

## Authenticated scraping (default, recommended)

`/hub/metrics` requires a JupyterHub token. The `ServiceMonitor` authorization
block makes the chart create a token secret (`<release>-metrics-token`) in the
monitoring namespace and scrape with a Bearer token. Annotation-based scraping
cannot attach the token — leave `serviceAnnotations` off in production.

## Useful Hub metrics

`hub_spawn_gpu_total`, `hub_spawn_failed_total`, `hub_active_sessions`,
`hub_session_runtime_minutes`, `hub_spawn_duration_seconds`,
`hub_quota_denied_total`, `hub_quota_deducted_total`, `hub_pod_failure_total`,
`hub_repo_clone_failed_total`. Alert rules cover `hub_spawn_failed_total` and
`hub_pod_failure_total`.

## Safety

- **Do not set `allowUnauthenticatedScrape: true` in production.** It exposes
  `/hub/metrics` without a token; only safe in an isolated dev cluster where the
  endpoint is never reachable via proxy/NodePort/LoadBalancer/Ingress.
- A `helm upgrade` restarts the Hub pod (brief login blip) — schedule around a
  live class.
- Don't commit any real metrics token; the chart manages the secret.
- Read-only verification (`scripts/verify_monitoring.sh`) only port-forwards;
  it makes no cluster changes.

## Reference

The full `monitoring.*` value reference, kube-prometheus-stack install,
existing-stack reuse, manual verification commands, and troubleshooting:
[reference.md](reference.md).
