# Monitor AUP Learning Cloud — Reference

The kube-prometheus-stack install, the full `monitoring.*` value reference,
existing-stack reuse, manual verification, and troubleshooting. Workflow and
gates are in [SKILL.md](SKILL.md).

## Source guide

- Monitoring Deployment Guide: <https://amdresearch.github.io/aup-learning-cloud/jupyterhub/monitoring.html>
- Configuration Reference (section 12): <https://amdresearch.github.io/aup-learning-cloud/jupyterhub/configuration-reference.html>

The chart ships the dashboards under `runtime/chart/dashboards/`; the live
`runtime/chart/values.schema.yaml` is the source of truth for the schema.

## Install kube-prometheus-stack (reference stack)

```bash
kubectl create namespace monitoring        # AlreadyExists is safe to ignore

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring

kubectl -n monitoring get pods
```

The release name `monitoring` makes the operator select `release: monitoring`,
matching the default `monitoring.releaseLabel`. If you use a different release
name or selector, set `monitoring.releaseLabel` to match.

## Reuse an existing Prometheus + Grafana

Confirm with the monitoring owner that:

- the Operator watches `ServiceMonitor` in the `monitoring` namespace,
- Prometheus may scrape services in `jupyterhub`,
- the operator's selector matches `release: <monitoring.releaseLabel>`,
- the Grafana sidecar reads dashboard ConfigMaps labelled `grafana_dashboard: "1"`
  from `monitoring`.

Example: if the stack selects `release: platform-monitoring`, set
`monitoring.releaseLabel: platform-monitoring`.

## monitoring.* value reference

| Value | Meaning |
| --- | --- |
| `monitoring.enabled` | Master switch for all monitoring objects |
| `monitoring.namespace` | Namespace the objects are created in (`monitoring`) |
| `monitoring.releaseLabel` | `release` label on ServiceMonitor/PrometheusRule; must match the operator selector |
| `monitoring.hubMetrics.enabled` | Hub metrics integration; also creates a metrics NetworkPolicy allowing the monitoring ns to reach the Hub on `8081` |
| `monitoring.hubMetrics.allowUnauthenticatedScrape` | Allow `/hub/metrics` without a token — dev only |
| `monitoring.hubMetrics.serviceAnnotations.enabled` | Adds `prometheus.io/*` annotations; cannot carry the token — prefer the ServiceMonitor path |
| `monitoring.serviceMonitor.enabled` | Creates `ServiceMonitor` `hub-metrics` selecting `component: hub`, port `8081`, path `<hub.baseUrl>/hub/metrics` |
| `monitoring.serviceMonitor.interval` | Scrape interval, e.g. `15s` |
| `monitoring.serviceMonitor.authorization.enabled` | Authenticated scraping (keep on) |
| `monitoring.serviceMonitor.authorization.type` | Default `Bearer` |
| `monitoring.serviceMonitor.authorization.hubServiceName` | Hub service account for the token; default `prometheus-metrics` must match `hub.services` + `hub.loadRoles` (`read:metrics`) |
| `monitoring.serviceMonitor.authorization.secret.create` | Create the token secret in the monitoring ns |
| `monitoring.serviceMonitor.authorization.secret.name` | Custom/existing secret name; blank = `<release>-metrics-token` |
| `monitoring.serviceMonitor.authorization.secret.key` | Secret key; default `token` |
| `monitoring.grafana.dashboard.enabled` | Creates dashboard ConfigMaps labelled `grafana_dashboard: "1"` |
| `monitoring.prometheusRule.enabled` | Creates alert rules for `hub_spawn_failed_total`, `hub_pod_failure_total` |

## Apply

```bash
helm upgrade --install jupyterhub ./runtime/chart -n jupyterhub \
  -f runtime/values.yaml -f <overlay>
# include any local overlay too, e.g. -f runtime/values.local.yaml
```

## Manual verification

```bash
kubectl -n monitoring get servicemonitor hub-metrics
kubectl -n monitoring get secret | grep metrics-token
kubectl -n monitoring get configmap grafana-dashboard-aup-hub
kubectl -n jupyterhub  get networkpolicy hub-metrics
# alerts, if enabled:
kubectl -n monitoring get prometheusrule hub-alerts

# Is the target UP?
kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090 &
curl -fsSL 'http://127.0.0.1:9090/api/v1/query?query=up%7Bjob%3D%22hub%22%7D'
# open http://127.0.0.1:9090/targets and look for hub-metrics = UP
```

A healthy query returns `"job":"hub"`, `"namespace":"jupyterhub"`, value `"1"`.
The dashboard ConfigMap should contain `aup-hub-operations.json` and
`aup-hub-notebook-resources.json`.

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| ServiceMonitor exists but no scraping | `release` label mismatch | `kubectl -n monitoring get servicemonitor hub-metrics --show-labels`; fix `releaseLabel`, re-apply |
| Target DOWN / Unauthorized | Annotation scraping or auth disabled | Use `serviceMonitor.authorization.enabled: true`, `serviceAnnotations` off |
| Token secret missing | Auth/secret create not enabled, or `hubServiceName` invalid | Enable `secret.create`; ensure `hubServiceName` exists under `hub.services` with `read:metrics` |
| Grafana dashboards absent | Sidecar not watching ns/label | ConfigMap label `grafana_dashboard: "1"`; sidecar must watch `monitoring` |
| Alerts absent | Rule ns/label not watched | `kubectl -n monitoring get prometheusrule hub-alerts --show-labels`; match the operator's rule selector |
