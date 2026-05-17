# Security Stack

This directory contains GitOps resources for security visibility controls.

Scope in this phase:
- Kyverno (controller)
- Kyverno audit-only policies
- Trivy Operator
- Policy Reporter
- Prometheus rules for security signal
- Grafana dashboard provisioning

Non-goals in this phase:
- Enforce-mode admission policies
- Kyverno mutate policies
- Runtime detection (Falco)
- Default-deny NetworkPolicy rollout

Operational model:
- Everything is managed by ArgoCD `Application` manifests under `installs/`.
- Generated reports (PolicyReport, VulnerabilityReport, etc.) are not managed as desired-state manifests.
- Alert severity is warning/high only in this phase.
- `ServerSideApply=true` is enabled in security ArgoCD Applications by default.

Namespace templates:
- Base namespace templates are provided in `apps/security/templates/namespaces-template.yaml`.
- Copy and customize as concrete manifests if namespace-level labels/annotations need to be managed explicitly.
