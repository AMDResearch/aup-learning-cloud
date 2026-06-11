# Monitoring Deployment Guide

This guide shows how to connect AUP Learning Cloud to a Prometheus and Grafana monitoring stack. It uses `kube-prometheus-stack` as the recommended example, then shows how to reuse an existing Prometheus Operator and Grafana deployment.

The AUP Learning Cloud Helm chart can create the monitoring resources needed for Hub metrics: a `ServiceMonitor`, optional Grafana dashboard ConfigMaps, optional Prometheus alert rules, a metrics `NetworkPolicy`, and an authenticated token secret when authenticated scraping is enabled.

<!-- TODO: Add architecture diagram showing AUP Learning Cloud Hub metrics scraped by Prometheus Operator and displayed in Grafana. -->
<!-- ![AUP Learning Cloud Monitoring Architecture](./images/monitoring-1-architecture.png) -->

## Prerequisites

- A Kubernetes cluster with AUP Learning Cloud installed or ready to install.
- `kubectl` access with permission to create resources in the `monitoring` and `jupyterhub` namespaces.
- Helm 3 installed locally.
- Access to the AUP Learning Cloud deployment repository that contains `runtime/values.yaml` and `runtime/chart`.

## Install kube-prometheus-stack

`kube-prometheus-stack` is the recommended reference deployment for Prometheus Operator, Prometheus, Alertmanager, and Grafana.

Artifact Hub page: <https://artifacthub.io/packages/helm/prometheus-community/kube-prometheus-stack>

### 1. Create the monitoring namespace

```bash
kubectl create namespace monitoring
```

If the namespace already exists, this command can return an `AlreadyExists` error. That is safe to ignore.

### 2. Add the Helm repository

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
```

### 3. Install the stack

Use the Helm release name `monitoring` in the `monitoring` namespace. This matches the default AUP Learning Cloud `monitoring.releaseLabel: monitoring` value.

```bash
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring
```

The Prometheus Operator installed by this stack usually selects `ServiceMonitor` and `PrometheusRule` objects with the label `release: monitoring`. If you use a different Helm release name or custom selector, update `monitoring.releaseLabel` in AUP Learning Cloud to match that selector.

<!-- TODO: Add diagram or screenshot showing the ServiceMonitor label selector relationship, especially release: monitoring. -->
<!-- ![ServiceMonitor Label Selector](./images/monitoring-2-servicemonitor-labels.png) -->

### 4. Check the monitoring pods

```bash
kubectl -n monitoring get pods
kubectl -n monitoring get svc
```

Wait until the Prometheus Operator, Prometheus, and Grafana pods are running.

A working `kube-prometheus-stack` deployment should include pods similar to these:

```text
alertmanager-monitoring-kube-prometheus-alertmanager-0   2/2   Running
monitoring-grafana-...                                  3/3   Running
monitoring-kube-prometheus-operator-...                 1/1   Running
monitoring-kube-state-metrics-...                       1/1   Running
prometheus-monitoring-kube-prometheus-prometheus-0       2/2   Running
```

The exact pod names and replica counts depend on the chart version and your cluster configuration.

## Reuse an Existing Prometheus and Grafana Stack

If your cluster already has Prometheus Operator and Grafana, you don't need to install `kube-prometheus-stack` again. Instead, confirm these points with the monitoring owner:

- The Prometheus Operator watches `ServiceMonitor` resources in the `monitoring` namespace.
- Prometheus can scrape services in the `jupyterhub` namespace.
- The operator selector matches the label used by AUP Learning Cloud. The chart creates `ServiceMonitor` and `PrometheusRule` resources with `release: <monitoring.releaseLabel>`.
- Grafana sidecar dashboard discovery reads ConfigMaps from the `monitoring` namespace with `grafana_dashboard: "1"`, if you want the AUP Learning Cloud dashboards to appear automatically.

For example, if the existing Prometheus stack selects `release: platform-monitoring`, set:

```yaml
monitoring:
  releaseLabel: platform-monitoring
```

## Configure AUP Learning Cloud Monitoring Values

Edit `runtime/values.yaml` and enable the monitoring options you need.

Recommended production configuration:

```yaml
monitoring:
  enabled: true
  namespace: monitoring
  releaseLabel: monitoring

  hubMetrics:
    enabled: true
    allowUnauthenticatedScrape: false
    serviceAnnotations:
      enabled: false

  serviceMonitor:
    enabled: true
    interval: 15s
    authorization:
      enabled: true
      type: Bearer
      hubServiceName: prometheus-metrics
      secret:
        create: true
        name: ""
        key: token

  grafana:
    dashboard:
      enabled: true

  prometheusRule:
    enabled: true
```

### Value Reference

| Value | Description |
|-------|-------------|
| `monitoring.enabled` | Master switch for AUP Learning Cloud monitoring resources. Keep this `true` when enabling any monitoring feature below. |
| `monitoring.namespace` | Namespace where monitoring objects are created. Use `monitoring` for the stack shown in this guide. |
| `monitoring.releaseLabel` | Value used for the `release` label on `ServiceMonitor` and `PrometheusRule`. It must match the label selected by your Prometheus Operator stack. For a Helm release named `monitoring`, this is commonly `release: monitoring`. |
| `monitoring.hubMetrics.enabled` | Enables Hub metrics integration. The chart also creates a metrics `NetworkPolicy` allowing traffic from the monitoring namespace to the Hub on port `8081`. |
| `monitoring.hubMetrics.allowUnauthenticatedScrape` | Allows `/hub/metrics` scraping without a JupyterHub token when set to `true`. Don't enable this in production unless `/hub/metrics` is guaranteed not to be exposed through a public proxy, NodePort, LoadBalancer, or Ingress. |
| `monitoring.hubMetrics.serviceAnnotations.enabled` | Adds `prometheus.io/scrape`, `prometheus.io/path`, and `prometheus.io/port` annotations to the Hub service. Annotation-based scraping cannot attach the JupyterHub token, so prefer the authenticated `ServiceMonitor` path. |
| `monitoring.serviceMonitor.enabled` | Creates a `ServiceMonitor` named `hub-metrics` in `monitoring.namespace`. It selects the Hub service in the `jupyterhub` namespace by `component: hub`, scrapes target port `8081`, and uses `<hub.baseUrl>/hub/metrics` as the path. |
| `monitoring.serviceMonitor.interval` | Scrape interval for the Hub metrics endpoint, such as `15s`. |
| `monitoring.serviceMonitor.authorization.enabled` | Adds ServiceMonitor authorization settings. Keep this `true` for authenticated scraping. |
| `monitoring.serviceMonitor.authorization.type` | Authorization type passed to the ServiceMonitor. The default is `Bearer`. |
| `monitoring.serviceMonitor.authorization.hubServiceName` | JupyterHub service account used for the metrics token. The default `prometheus-metrics` must match `hub.services.prometheus-metrics` and `hub.loadRoles.prometheus-metrics`, which grants `read:metrics`. |
| `monitoring.serviceMonitor.authorization.secret.create` | Creates a token secret in the monitoring namespace when set to `true`. |
| `monitoring.serviceMonitor.authorization.secret.name` | Optional existing or custom secret name. Leave empty to use the chart-generated `<hub fullname>-metrics-token` name. |
| `monitoring.serviceMonitor.authorization.secret.key` | Secret key that stores the token. The default is `token`. |
| `monitoring.grafana.dashboard.enabled` | Creates Grafana dashboard ConfigMaps in the monitoring namespace with label `grafana_dashboard: "1"`. |
| `monitoring.prometheusRule.enabled` | Creates Prometheus alert rules for `hub_spawn_failed_total` and `hub_pod_failure_total`. |

## Apply the AUP Learning Cloud Configuration

Run the upgrade from the deployment repository root.

```bash
cd deploy
helm upgrade jupyterhub ../runtime/chart --namespace jupyterhub \
  -f ../runtime/values.yaml
```

If your deployment uses an additional local or environment-specific values file, include it in the same command. For example:

```bash
helm upgrade jupyterhub ../runtime/chart --namespace jupyterhub \
  -f ../runtime/values.yaml -f ../runtime/values.local.yaml
```

## Verify the Setup

Check that the AUP Learning Cloud monitoring resources exist:

```bash
kubectl -n monitoring get servicemonitor hub-metrics
kubectl -n monitoring get secret | grep metrics-token
kubectl -n monitoring get configmap grafana-dashboard-aup-hub
kubectl -n jupyterhub get networkpolicy hub-metrics
```

If `monitoring.prometheusRule.enabled: true`, also check the Hub alert rule:

```bash
kubectl -n monitoring get prometheusrule hub-alerts
```

A working cluster with ServiceMonitor, authenticated scraping, Grafana dashboards, and metrics NetworkPolicy enabled should show objects like this:

```text
servicemonitor.monitoring.coreos.com/hub-metrics
secret/hub-metrics-token
configmap/grafana-dashboard-aup-hub
networkpolicy.networking.k8s.io/hub-metrics
```

Check that Prometheus sees the Hub target:

```bash
kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090
```

Open `http://127.0.0.1:9090/targets` and look for the `hub-metrics` target. It should be `UP`.

You can also verify from the Prometheus API. With the port-forward still running, query the Hub scrape target:

```bash
curl -fsSL 'http://127.0.0.1:9090/api/v1/query?query=up%7Bjob%3D%22hub%22%7D'
```

A healthy result contains `"job":"hub"`, `"namespace":"jupyterhub"`, and a final value of `"1"`:

```json
{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      {
        "metric": {
          "job": "hub",
          "namespace": "jupyterhub",
          "service": "hub"
        },
        "value": ["<timestamp>", "1"]
      }
    ]
  }
}
```

Check that Grafana can discover the AUP Learning Cloud dashboards through the dashboard ConfigMap:

```bash
kubectl -n monitoring describe configmap grafana-dashboard-aup-hub
```

The ConfigMap should contain these dashboard files:

```text
aup-hub-operations.json
aup-hub-notebook-resources.json
```

If your Grafana deployment uses the standard sidecar dashboard loader, these ConfigMaps are enough. You do not need to expose Grafana publicly just to validate this step.

Useful AUP Learning Cloud Hub metrics include:

- `hub_spawn_gpu_total`
- `hub_spawn_failed_total`
- `hub_active_sessions`
- `hub_session_runtime_minutes`
- `hub_spawn_duration_seconds`
- `hub_quota_denied_total`
- `hub_quota_deducted_total`
- `hub_pod_failure_total`
- `hub_repo_clone_failed_total`

## Troubleshooting

### ServiceMonitor Exists but Prometheus Does Not Scrape It

Check the `release` label:

```bash
kubectl -n monitoring get servicemonitor hub-metrics --show-labels
```

If Prometheus expects a different label, update `monitoring.releaseLabel` and run the Helm upgrade again.

### Target Is Down or Returns Unauthorized

Use authenticated ServiceMonitor scraping in production:

```yaml
monitoring:
  hubMetrics:
    allowUnauthenticatedScrape: false
    serviceAnnotations:
      enabled: false
  serviceMonitor:
    enabled: true
    authorization:
      enabled: true
```

Annotation-based scraping cannot attach the JupyterHub token. It only works when unauthenticated metrics scraping is allowed, which should be limited to isolated development environments.

### Token Secret Is Missing

Confirm these values are enabled:

```yaml
monitoring:
  enabled: true
  hubMetrics:
    enabled: true
  serviceMonitor:
    enabled: true
    authorization:
      enabled: true
      secret:
        create: true
```

The chart also validates that `monitoring.serviceMonitor.authorization.hubServiceName` exists under `hub.services` and has a matching `hub.loadRoles` entry with the `read:metrics` scope.

### Grafana Dashboards Do Not Appear

Check that the dashboard ConfigMap was created:

```bash
kubectl -n monitoring get configmap grafana-dashboard-aup-hub --show-labels
```

The ConfigMap uses `grafana_dashboard: "1"`. Your Grafana sidecar or dashboard loader must watch the `monitoring` namespace and this label.

### Prometheus Alerts Do Not Appear

Check the rule label and namespace:

```bash
kubectl -n monitoring get prometheusrule hub-alerts --show-labels
```

The rule must be in a namespace watched by the Prometheus Operator, and its `release` label must match the operator's rule selector.
