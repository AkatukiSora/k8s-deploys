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
