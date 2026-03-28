#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${1:-staging}"
BACKEND_IMAGE="${2:-}"
FRONTEND_IMAGE="${3:-}"

if [[ -z "${BACKEND_IMAGE}" || -z "${FRONTEND_IMAGE}" ]]; then
  echo "Usage: scripts/deploy_k8s.sh <staging|production> <backend-image> <frontend-image>"
  exit 1
fi

if [[ "${ENVIRONMENT}" != "staging" && "${ENVIRONMENT}" != "production" ]]; then
  echo "Environment must be staging or production"
  exit 1
fi

NAMESPACE="sar-${ENVIRONMENT}"
OVERLAY_PATH="k8s/overlays/${ENVIRONMENT}"

echo "Applying manifests from ${OVERLAY_PATH} into ${NAMESPACE}"
if ! kubectl apply -k "${OVERLAY_PATH}"; then
  echo "Standard apply failed, retrying with --validate=false"
  kubectl apply --validate=false -k "${OVERLAY_PATH}"
fi

echo "Setting workload images"
kubectl -n "${NAMESPACE}" set image deployment/sar-backend backend="${BACKEND_IMAGE}"
kubectl -n "${NAMESPACE}" set image deployment/sar-frontend frontend="${FRONTEND_IMAGE}"

echo "Waiting for rollouts"
kubectl -n "${NAMESPACE}" rollout status deployment/sar-backend --timeout=300s
kubectl -n "${NAMESPACE}" rollout status deployment/sar-frontend --timeout=300s

echo "Deployment successful for ${ENVIRONMENT}"
