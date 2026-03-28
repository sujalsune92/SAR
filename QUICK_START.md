# Quick Start Guide - Docker Setup

## 30-Second Start

```bash
cd c:\new_sar\SAR
docker-compose up --build
```

Then open: **http://localhost**

**Login**: analyst / password123

---

## First-Run Checklist

- [ ] Docker Desktop is installed and running
- [ ] 8+ GB RAM available
- [ ] 20+ GB free disk space
- [ ] Terminal/PowerShell in project root

## What Happens When You Run the Command

1. ✅ Builds Backend Docker image (0.5min)
2. ✅ Builds Frontend Docker image (0.5min)
3. ✅ Starts PostgreSQL (1-2min)
4. ✅ Starts Ollama service (1-2min)
5. ✅ Pulls Ollama model mistral:7b (~4GB, 3-5min on first run)
6. ✅ Initializes database and seeds data
7. ✅ Starts Backend
8. ✅ Starts Frontend

**Total First Run**: ~10-15 minutes  
**Subsequent Runs**: ~30-60 seconds

---

## Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost | Main UI |
| Backend API | http://localhost:8000 | REST API |
| API Docs | http://localhost:8000/docs | Swagger UI |
| API ReDoc | http://localhost:8000/redoc | Alternative Docs |

---

## Common Commands

```bash
# View logs
docker-compose logs -f

# View backend logs only
docker-compose logs -f backend

# Stop everything
docker-compose down

# Stop and delete all data
docker-compose down -v

# Rebuild backend only
docker-compose build --no-cache backend
docker-compose up backend

# Access backend shell
docker-compose exec backend bash

# Access database
docker-compose exec postgres psql -U postgres -d sar_audit

# See running containers
docker-compose ps

# Pull a different Ollama model
docker-compose exec ollama ollama pull llama2:7b
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Connection refused" | Wait 30-60s for database, check `docker-compose logs postgres` |
| "Model not found" | Run: `docker-compose exec ollama ollama pull mistral:7b` |
| Port already in use | Edit `.env.docker` - change BACKEND_PORT or FRONTEND_PORT |
| Frontend blank | Check browser console (F12), ensure backend is running |
| Out of memory | Increase Docker memory limit in Docker Desktop settings |

---

## Stop & Clean Up

```bash
# Keep data (safe to restart)
docker-compose down

# Delete everything (fresh start)
docker-compose down -v

# Remove stopped containers
docker-compose rm

# Prune unused images/volumes
docker system prune -a -v
```

---

## Configuration

Edit `.env.docker` to customize:

```env
# Database
POSTGRES_PASSWORD=postgres          # Change for production
POSTGRES_DB=sar_audit

# Backend
BACKEND_PORT=8000                   # Change if port in use
OLLAMA_MODEL=mistral:7b             # Or: llama2, neural-chat, etc.
JWT_SECRET_KEY=change-in-production # CHANGE FOR PRODUCTION

# Frontend
FRONTEND_PORT=80                    # Change if port in use
```

Then restart: `docker-compose up --build`

---

## Production Setup

Before going live:

```bash
# 1. Copy template
cp .env.docker .env.production

# 2. Edit with secure values
nano .env.production

# 3. Deploy
docker-compose --env-file .env.production up -d
```

**DO NOT skip these production steps:**
- [ ] Change JWT_SECRET_KEY
- [ ] Change POSTGRES_PASSWORD
- [ ] Enable HTTPS in nginx.conf
- [ ] Restrict CORS origins in backend/app.py
- [ ] Update database credentials in .env.production

---

## Full Documentation

For detailed information, see:
- **DOCKER_SETUP.md** - Complete setup guide with architecture
- **DOCKER_MIGRATION.md** - Summary of all changes made
- **README.md** - Original project documentation

---

## Support

If something goes wrong:

1. Check logs: `docker-compose logs -f`
2. Verify services: `docker-compose ps`
3. Restart: `docker-compose down && docker-compose up --build`
4. Clean restart: `docker-compose down -v && docker-compose up --build`

---

**Ready?** Run: `docker-compose up --build` 🚀
