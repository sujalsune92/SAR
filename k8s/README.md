# Kubernetes Deployment

This directory contains Kustomize-based manifests for SAR deployment.

## Layout

- `base/`: reusable workloads and services.
- `overlays/staging/`: staging-specific hostnames and scaling.
- `overlays/production/`: production-specific hostnames and scaling.

## Prerequisites

1. Kubernetes cluster with ingress controller.
2. Namespace access for `sar-staging` and `sar-production`.
3. Secret named `sar-secrets` in each namespace.
4. Container registry pull access for backend/frontend images.

## Create secrets

Do not commit real values. Create directly in cluster:

```bash
kubectl create namespace sar-staging --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace sar-production --dry-run=client -o yaml | kubectl apply -f -

kubectl -n sar-staging create secret generic sar-secrets \
  --from-literal=JWT_SECRET_KEY='replace' \
  --from-literal=POSTGRES_USER='postgres' \
  --from-literal=POSTGRES_PASSWORD='replace' \
  --from-literal=POSTGRES_DB='sar_audit' \
  --from-literal=DATABASE_URL='postgresql://postgres:replace@postgres:5432/sar_audit'

kubectl -n sar-production create secret generic sar-secrets \
  --from-literal=JWT_SECRET_KEY='replace' \
  --from-literal=POSTGRES_USER='postgres' \
  --from-literal=POSTGRES_PASSWORD='replace' \
  --from-literal=POSTGRES_DB='sar_audit' \
  --from-literal=DATABASE_URL='postgresql://postgres:replace@postgres:5432/sar_audit'
```

## Deploy manually

```bash
kubectl apply -k k8s/overlays/staging
kubectl apply -k k8s/overlays/production
```

## Rollback

```bash
kubectl -n sar-staging rollout undo deployment/sar-backend
kubectl -n sar-staging rollout undo deployment/sar-frontend

kubectl -n sar-production rollout undo deployment/sar-backend
kubectl -n sar-production rollout undo deployment/sar-frontend
```
