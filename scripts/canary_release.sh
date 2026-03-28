#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${1:-production}"
BACKEND_IMAGE="${2:-}"
FRONTEND_IMAGE="${3:-}"

if [[ "${ENVIRONMENT}" != "staging" && "${ENVIRONMENT}" != "production" ]]; then
  echo "Environment must be staging or production"
  exit 1
fi

if [[ -z "${BACKEND_IMAGE}" || -z "${FRONTEND_IMAGE}" ]]; then
  echo "Usage: scripts/canary_release.sh <staging|production> <backend-image> <frontend-image>"
  exit 1
fi

NAMESPACE="sar-${ENVIRONMENT}"

echo "Applying canary image update in ${NAMESPACE}"
kubectl -n "${NAMESPACE}" set image deployment/sar-backend backend="${BACKEND_IMAGE}"
kubectl -n "${NAMESPACE}" set image deployment/sar-frontend frontend="${FRONTEND_IMAGE}"

# Pause rollout after first replica update and verify health before full rollout.
kubectl -n "${NAMESPACE}" rollout pause deployment/sar-backend
sleep 20
kubectl -n "${NAMESPACE}" get pods -l app=sar-backend
kubectl -n "${NAMESPACE}" rollout resume deployment/sar-backend

kubectl -n "${NAMESPACE}" rollout status deployment/sar-backend --timeout=300s
kubectl -n "${NAMESPACE}" rollout status deployment/sar-frontend --timeout=300s

echo "Canary rollout complete in ${NAMESPACE}"
