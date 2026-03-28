# Monitoring and Logging

This project includes an observability stack with:

- Prometheus for metrics
- Alertmanager for notifications
- Grafana for dashboards
- Loki + Promtail for centralized logs

## Run stack with application

1. Start app services first:

```bash
docker-compose up -d
```

2. Start observability services:

```bash
docker-compose -f docker-compose.observability.yml up -d
```

## Access

- Prometheus: http://localhost:9090
- Alertmanager: http://localhost:9093
- Grafana: http://localhost:3000 (admin/admin)
- Loki API: http://localhost:3100

## Notes

- Backend metrics are exposed on `/metrics`.
- Default alert manager receiver is a webhook placeholder.
- Replace webhook URL and Grafana credentials before production usage.
