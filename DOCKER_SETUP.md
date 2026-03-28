# Docker Compose Setup Guide

## Quick Start

### Prerequisites
- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Docker Compose (included with Docker Desktop)
- At least 8GB RAM (recommendedfor Ollama)
- 20GB free disk space (for Ollama models and databases)

### To Run the Application

```bash
# 1. Navigate to project root
cd c:\new_sar\SAR

# 2. Start all services
docker-compose up --build

# 3. Access the application
- Frontend: http://localhost (or http://localhost:80)
- Backend API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

# 4. Stop the application
docker-compose down

# 5. Stop and remove volumes (WARNING: deletes data)
docker-compose down -v
```

## Default Credentials

- **Username**: analyst, manager, or admin
- **Password**: password123

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Docker Network                    │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │  Frontend (Nginx:80)                         │  │
│  │  - Serves static HTML/CSS/JS                │  │
│  │  - Proxies API calls to Backend             │  │
│  └──────────────────────────────────────────────┘  │
│                      ↓                              │
│  ┌──────────────────────────────────────────────┐  │
│  │  Backend (FastAPI:8000)                      │  │
│  │  - JWT Authentication                       │  │
│  │  - Case Management API                      │  │
│  │  - PDF Export                               │  │
│  └──────────────────────────────────────────────┘  │
│         ↓            ↓            ↓                │
│    ┌────────┐   ┌────────┐   ┌────────┐          │
│    │PostgreSQL   │ChromaDB  │ Ollama  │          │
│    │(Database)   │(Vector DB)│(LLM)  │          │
│    └────────┘   └────────┘   └────────┘          │
│                                                      │
└─────────────────────────────────────────────────────┘
```

## Service Details

### PostgreSQL (postgres:5432)
- **Image**: postgres:15-alpine
- **Credentials**: postgres/postgres (from .env.docker)
- **Database**: sar_audit
- **Volume**: postgres_data (persists data)
- **Health Check**: Every 10s

### Ollama (ollama:11434)
- **Image**: ollama/ollama:latest
- **Default Model**: mistral:7b
- **Volume**: ollama_data (persists models)
- **Note**: First pull may take 5-10 minutes

### Backend (backend:8000)
- **Port**: 8000
- **Depends On**: postgres, ollama
- **Environment**: Set from .env.docker
- **Health Check**: FastAPI /docs endpoint

### Frontend (frontend:80)
- **Port**: 80
- **Depends On**: backend
- **Serves**: Static files from /frontend
- **Proxies**: API calls to backend

## Common Tasks

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f postgres
docker-compose logs -f ollama
```

### Access Backend Shell
```bash
docker-compose exec backend bash
# Inside container:
python -m pytest tests/ -v
python -c "from backend.database import init_db; init_db()"
```

### Access Database Shell
```bash
docker-compose exec postgres psql -U postgres -d sar_audit
```

### Rebuild Specific Service
```bash
docker-compose build --no-cache backend
docker-compose up backend
```

### Access Saved Models in Ollama
```bash
docker-compose exec ollama ollama list
```

## Environment Variables

Edit `.env.docker` to customize:

```env
# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=sar_audit
POSTGRES_PORT=5432

# Backend
BACKEND_PORT=8000
OLLAMA_MODEL=mistral:7b
JWT_SECRET_KEY=change-in-production

# Frontend
FRONTEND_PORT=80

# Application
ENVIRONMENT=development
LOG_LEVEL=info
```

## Manual Steps Required

### 1. First-Time Setup
When you first run `docker-compose up --build`, the following happens automatically:
- PostgreSQL database is created and initialized
- Backend tables are created
- Sample data is seeded (optional, see SKIP below)
- Ollama service starts

However, **you may need to manually pull the Ollama model on first run**:

```bash
# While containers are running
docker-compose exec ollama ollama pull mistral:7b
```

Or run before starting backend:
```bash
docker-compose up postgres ollama
# Wait for both to be ready
docker-compose exec ollama ollama pull mistral:7b
docker-compose up --build backend frontend
```

### 2. Skip Auto-Seeding (Optional)
If you don't want auto-seeding, comment out these lines in docker-compose.yml:
```yaml
command: >
  sh -c "python -m pytest tests/ -v || true && 
         uvicorn backend.app:app --host 0.0.0.0 --port 8000"
```

Change to:
```yaml
command: ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3. Use Different Ollama Model
```bash
# Set in .env.docker
OLLAMA_MODEL=llama2:7b

# Or override when starting
docker-compose up --build -e OLLAMA_MODEL=llama2:7b
```

Available models: llama2, neural-chat, mistral, etc.

### 4. Production Configuration
Before deploying to production:

1. **Change JWT_SECRET_KEY** in .env.docker
2. **Change database passwords** - use strong credentials
3. **Use environment-specific .env files**:
   ```bash
   cp .env.docker .env.production
   # Edit .env.production with production values
   docker-compose --env-file .env.production up
   ```
4. **Enable HTTPS** - update nginx.conf with SSL certificates
5. **Restrict CORS** - update backend app.py CORS origins
6. **Use health checks** - monitor containers with Docker health checks
7. **Set resource limits** in docker-compose.yml:
   ```yaml
   services:
     backend:
       deploy:
         resources:
           limits:
             cpus: '1'
             memory: 2G
   ```

## Troubleshooting

### Backend won't start - "Connection refused to postgres"
```
Solution: PostgreSQL service is still starting. Docker will retry automatically.
Wait 30-60 seconds for database to initialize, or:
docker-compose logs postgres
```

### "Model not found" error
```
Solution: Ollama model hasn't been pulled yet:
docker-compose exec ollama ollama pull mistral:7b
```

### Port already in use (ERROR binding port 8000)
```
Solution: Change port in .env.docker or stop conflicting service:
docker ps
docker stop <container-id>
# OR
BACKEND_PORT=8001 docker-compose up --build
```

### Frontend shows blank page
```
Solution: Check browser console for API errors:
1. Browser DevTools → Console
2. Verify API_BASE in frontend/api.js matches the backend URL
3. Check docker-compose logs frontend
```

### Database migration errors
```
Solution: Rebuild and reinitialize:
docker-compose down -v
docker-compose up --build
```

### Out of memory (OOM killed)
```
Solution: Increase Docker memory limit (Docker Desktop Settings)
Or reduce Ollama model size in .env.docker:
OLLAMA_MODEL=phi:latest  # smaller model
```

### Can't access Ollama from backend
```
Solution: Ensure OLLAMA_HOST is set correctly:
- In docker-compose.yml: OLLAMA_HOST=http://ollama:11434
- Check docker-compose logs backend for connection errors
- Verify ollama container is running: docker-compose ps
```

## Assumptions Made

1. **PostgreSQL as primary database**: Application expects a PostgreSQL instance
2. **Ollama for LLM**: Uses local Ollama with mistral:7b by default
3. **ChromaDB persistence**: Vector data stored locally in vector_db/ directory
4. **Nginx for frontend**: Static file serving and API proxying
5. **Docker network**: Services communicate via service names (postgres, ollama, backend)
6. **Volumes preserved**: Database and Ollama data persists across container restarts
7. **CORS enabled for development**: More permissive than production

## File Structure

```
SAR/
├── Dockerfile.backend          # Backend container definition
├── Dockerfile.frontend         # Frontend container definition
├── docker-compose.yml          # Orchestration configuration
├── nginx.conf                  # Nginx proxy configuration
├── .dockerignore              # Docker build ignore patterns
├── .env.docker                # Environment variables for Docker
├── docker-entrypoint.sh       # Initialization script (optional)
├── DOCKER_SETUP.md            # This file
├── backend/
│   ├── app.py                 # FastAPI application
│   ├── database.py            # PostgreSQL handlers
│   ├── schemas.py             # Pydantic models
│   └── enrichment.py          # Data enrichment
├── frontend/
│   ├── index.html             # Login page
│   ├── dashboard.html         # Main dashboard
│   ├── api.js                 # API client (updated for Docker)
│   └── style.css              # Styling
├── rag_pipeline/
│   ├── pipeline_service.py    # RAG orchestration
│   ├── rule_engine.py         # AML rules
│   └── vector_db/             # ChromaDB data
└── scripts/
    ├── seed_data.py           # Database seeding
    └── ensure_local_postgres.py
```

## Performance Tips

1. **Use Alpine Linux images** (already in docker-compose.yml)
2. **Limit Ollama model**: Smaller models = faster inference
3. **Persistent volumes**: Data persists without re-seeding
4. **Health checks**: Services restart if unhealthy
5. **Resource limits**: Set CPU/memory constraints in production

## Support and Debugging

For detailed service status:
```bash
docker-compose ps
docker inspect sar-backend
docker-compose exec backend env
```

To verify network connectivity between services:
```bash
docker-compose exec backend ping ollama
docker-compose exec backend nc -zv ollama 11434
```

To test API endpoints directly from container:
```bash
docker-compose exec backend curl -s http://localhost:8000/docs | head -50
```

## Next Steps

1. Run `docker-compose up --build`
2. Wait for all services to be healthy (~60-90 seconds)
3. Access http://localhost
4. Login with analyst/password123
5. Create a new SAR case
6. Monitor logs: `docker-compose logs -f backend`

---
Generated: March 28, 2026
For issues or updates, refer to README.md or project documentation.
