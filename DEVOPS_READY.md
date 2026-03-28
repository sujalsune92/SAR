# DevOps-Ready Blueprint

This project is now structured for repeatable CI/CD, containerization, Kubernetes deployments, observability, rollback, and controlled promotions.

## 1. Project Analysis Summary

- Runtime: Python 3.11 FastAPI backend, static frontend (Nginx), PostgreSQL, Ollama, ChromaDB.
- Existing containers: backend, frontend, postgres, ollama already present.
- Tests: pytest suites under `tests/`.
- Deployment target: Kubernetes with Kustomize overlays for staging and production.
- CI/CD target: GitHub Actions with staged promotion and production approval gate.

## 2. Files Added and What They Do

### CI/CD and Quality

- `.github/workflows/ci-cd.yml`
  - Runs lint (`ruff`) and tests (`pytest`) on PR/push.
  - Builds and pushes backend/frontend images to GHCR.
  - Deploys automatically to staging from `main`.
  - Deploys to production only through `production` environment approval.
  - Includes rollback steps and Slack webhook notifications on failures.

- `requirements-dev.txt`
  - Dev/CI tooling: ruff and pytest tooling.

- `pyproject.toml`
  - Ruff lint rules and pytest defaults.

### Security and Environment Management

- `.env.example`
  - Local development env template.

- `.env.production.example`
  - Production template with placeholders for secret manager values.

### Kubernetes Deployment

- `k8s/base/*`
  - Core workloads and services:
    - backend deployment + probes + resources
    - frontend deployment + probes + resources
    - postgres statefulset + persistent storage
    - ollama deployment + persistent storage
    - ingress, HPA, configmap, PVCs
  - `secret.example.yaml` is a template only. Do not apply with real secrets in git.

- `k8s/overlays/staging/*`
  - Staging namespace (`sar-staging`), reduced replicas, staging ingress host.

- `k8s/overlays/production/*`
  - Production namespace (`sar-production`), higher replicas, production ingress host.

- `k8s/README.md`
  - Secret creation, deploy, and rollback commands.

### Deployment Automation

- `scripts/deploy_k8s.sh`
  - Applies overlay, sets exact image tags, waits for rollout.

- `scripts/rollback_k8s.sh`
  - Performs rollout undo and waits for stabilization.

### Monitoring and Logging

- `docker-compose.observability.yml`
  - Local observability stack (Prometheus, Alertmanager, Grafana, Loki, Promtail).

- `monitoring/*`
  - Prometheus scrape and alerts.
  - Alertmanager route/receiver config.
  - Loki and Promtail logging config.
  - Grafana data source provisioning.

- `k8s/monitoring/*`
  - Cluster observability namespace and deployments for Prometheus, Alertmanager, Loki, Grafana.
  - Scrapes both staging and production backend metrics endpoints.

## 3. Runtime Hardening Changes

- `backend/app.py`
  - JWT secret now loads from `JWT_SECRET_KEY` env var.
  - Prometheus metrics endpoint exposed via `prometheus-fastapi-instrumentator` (`/metrics`).

- `requirements.txt`
  - Added `prometheus-fastapi-instrumentator` dependency.

## 4. Secrets and Secure Configuration

Use GitHub Environments and Secrets:

- Required repository/environment secrets:
  - `KUBE_CONFIG_STAGING_B64`
  - `KUBE_CONFIG_PRODUCTION_B64`
  - `SLACK_WEBHOOK_URL` (optional but recommended)

Use Kubernetes Secrets for runtime credentials:

- `JWT_SECRET_KEY`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `DATABASE_URL`

Best practice:

1. Store secrets in cloud secret manager (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager).
2. Sync into Kubernetes secrets through your secret operator or deployment pipeline.
3. Never commit actual secrets into git.

## 5. Rollback Strategy

Automated:

- CI/CD jobs call rollback scripts on deployment failure.

Manual:

```bash
./scripts/rollback_k8s.sh staging
./scripts/rollback_k8s.sh production
```

Mechanism:

- Kubernetes `rollout undo` reverts to previous ReplicaSet.
- Pipeline waits for post-rollback health before marking complete.

## 6. Notifications

- Slack webhook notifications are triggered on staging/production deployment failures.
- Production success notification is also sent.

## 7. End-to-End Workflow Diagram

```text
Developer Push/PR
      |
      v
+-----------------------+
| GitHub Actions: CI    |
| - Ruff lint           |
| - Pytest tests        |
+-----------------------+
      |
      v
+-----------------------+
| Build Docker Images   |
| backend + frontend    |
| Push to GHCR          |
+-----------------------+
      |
      v
+-----------------------+
| Deploy Staging (auto) |
| k8s overlay/staging   |
| rollout status check  |
+-----------------------+
      |
      +-----> on failure: rollback + Slack alert
      |
      v
+-------------------------------+
| Production Approval Gate      |
| GitHub Environment: production|
+-------------------------------+
      |
      v
+--------------------------+
| Deploy Production        |
| k8s overlay/production   |
| rollout status + alerts  |
+--------------------------+
      |
      +-----> on failure: rollback + Slack alert
      |
      v
+--------------------------------+
| Observability                  |
| Prometheus + Alertmanager      |
| Grafana dashboards             |
| Loki/Promtail logs             |
+--------------------------------+
```

## 8. Setup Checklist

1. Configure GHCR package permissions for workflow token.
2. Create staging and production GitHub environments.
3. Add required environment secrets.
4. Protect `production` environment with required reviewer approval.
5. Create `sar-secrets` in both Kubernetes namespaces.
6. Deploy base app overlays.
7. Deploy monitoring stack (`k8s/monitoring` and/or docker observability compose).
8. Validate `/health` and `/metrics` from backend.
