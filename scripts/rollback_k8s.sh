#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${1:-staging}"

if [[ "${ENVIRONMENT}" != "staging" && "${ENVIRONMENT}" != "production" ]]; then
  echo "Environment must be staging or production"
  exit 1
fi

NAMESPACE="sar-${ENVIRONMENT}"

echo "Rolling back latest revisions in ${NAMESPACE}"
kubectl -n "${NAMESPACE}" rollout undo deployment/sar-backend
kubectl -n "${NAMESPACE}" rollout undo deployment/sar-frontend

echo "Waiting for rollback rollouts"
kubectl -n "${NAMESPACE}" rollout status deployment/sar-backend --timeout=300s
kubectl -n "${NAMESPACE}" rollout status deployment/sar-frontend --timeout=300s

echo "Rollback completed for ${ENVIRONMENT}"
