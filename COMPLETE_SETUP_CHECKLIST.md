# Complete Setup Checklist for Ubuntu VM

## Overview

After installing Docker, here's everything else you need to setup to get the application running.

---

## Setup Steps Checklist

### ✅ Step 1: Copy Project Files to VM

**From Windows (PowerShell):**
```powershell
# Navigate to project directory
cd C:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio

# Copy entire project to VM
scp -r . ubuntu@<VM_IP>:/home/ubuntu/aem-guides-dataset-studio
```

**Or use provided script:**
```powershell
.\copy-to-vm.ps1
```

**Verify files copied:**
```bash
# On VM
ls -la /home/ubuntu/aem-guides-dataset-studio
# Should see: docker-compose.yml, backend/, frontend/, etc.
```

---

### ✅ Step 2: Create Environment Configuration (.env file)

**On VM:**
```bash
cd /home/ubuntu/aem-guides-dataset-studio

# Create .env file (if .env.example exists)
cp .env.example .env

# Or create manually
nano .env
```

**Required Environment Variables:**
```bash
# Database Configuration
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/dataset_studio
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres  # ⚠️ Change for production!
POSTGRES_DB=dataset_studio
POSTGRES_PORT=5432

# Backend Configuration
BACKEND_PORT=8000
LOG_LEVEL=INFO
ENVIRONMENT=production
STRUCTURED_LOGGING=false

# Frontend Configuration
FRONTEND_PORT=80

# CORS Configuration
CORS_ORIGINS=*

# Redis Configuration
REDIS_URL=redis://redis:6379/0
REDIS_PORT=6379

# Storage Path (Linux)
STORAGE_PATH=/home/ubuntu/datasets

# Cleanup Configuration
CLEANUP_ENABLED=true
CLEANUP_DAYS_OLD=7
CLEANUP_SCHEDULE=0 2 * * *
```

**Important:** Change `POSTGRES_PASSWORD` for security!

---

### ✅ Step 3: Create Storage Directory

**On VM:**
```bash
# Create storage directory
mkdir -p /home/ubuntu/datasets

# Set permissions
chown -R ubuntu:ubuntu /home/ubuntu/datasets
chmod 755 /home/ubuntu/datasets

# Verify
ls -ld /home/ubuntu/datasets
```

**Purpose:** This is where generated datasets will be stored.

---

### ✅ Step 4: Configure Firewall

**On VM:**
```bash
# Allow SSH (if not already allowed)
sudo ufw allow 22/tcp comment 'SSH'

# Allow Frontend
sudo ufw allow 80/tcp comment 'Frontend HTTP'

# Allow Backend API
sudo ufw allow 8000/tcp comment 'Backend API'

# Optional: Allow PostgreSQL (if accessing externally)
sudo ufw allow 5432/tcp comment 'PostgreSQL'

# Enable firewall (if not already enabled)
sudo ufw enable

# Check status
sudo ufw status
```

**Expected Output:**
```
Status: active

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW       Anywhere
80/tcp                     ALLOW       Anywhere
8000/tcp                   ALLOW       Anywhere
```

---

### ✅ Step 5: Build Docker Images

**On VM:**
```bash
cd /home/ubuntu/aem-guides-dataset-studio

# Build all images (takes 5-10 minutes)
docker compose build

# Or build without cache (if issues)
docker compose build --no-cache
```

**What happens:**
- Backend image builds (Python dependencies, Node.js, etc.)
- Frontend image builds (React app, Nginx config)
- Base images downloaded (postgres, redis)

**Time:** 5-15 minutes depending on internet speed

---

### ✅ Step 6: Start Services

**On VM:**
```bash
cd /home/ubuntu/aem-guides-dataset-studio

# Start all services in background
docker compose up -d

# Check status
docker compose ps
```

**Expected Output:**
```
NAME                        STATUS              PORTS
dataset-studio-backend      Up                  0.0.0.0:8000->8000/tcp
dataset-studio-frontend     Up                  0.0.0.0:80->80/tcp
dataset-studio-db           Up (healthy)        0.0.0.0:5432->5432/tcp
dataset-studio-redis        Up (healthy)        0.0.0.0:6379->6379/tcp
```

---

### ✅ Step 7: Run Database Migrations

**On VM:**
```bash
# Migrations run automatically on backend startup
# But you can also run manually:

docker compose exec backend alembic upgrade head

# Or check if migrations ran
docker compose logs backend | grep -i migration
```

**What happens:**
- Creates `jobs` table
- Creates `saved_recipes` table
- Adds progress tracking columns (if migration exists)

**Verify:**
```bash
# Check database tables
docker compose exec postgres psql -U postgres -d dataset_studio -c "\dt"
```

---

### ✅ Step 8: Verify Services

**On VM:**
```bash
# 1. Check all containers are running
docker compose ps
# All should show "Up" status

# 2. Check backend health
curl http://localhost:8000/health
# Should return: {"status":"healthy",...}

# 3. Check frontend
curl http://localhost/
# Should return HTML content

# 4. Check database connection
docker compose exec backend python -c "from app.db.session import engine; engine.connect(); print('DB connected')"
# Should print: DB connected

# 5. View logs (if issues)
docker compose logs backend
docker compose logs frontend
```

---

### ✅ Step 9: Get VM IP Address

**On VM:**
```bash
# Get IP address
hostname -I
# Or
ip addr show | grep "inet " | grep -v 127.0.0.1
```

**Note IP address** - You'll need this to access from other machines.

---

### ✅ Step 10: Test Access from Browser

**From your local machine or team members:**

1. **Frontend**: `http://<VM_IP>/`
   - Should show the Dataset Generator UI

2. **Backend API**: `http://<VM_IP>:8000`
   - Should show API response

3. **API Docs**: `http://<VM_IP>:8000/docs`
   - Should show Swagger UI

4. **Health Check**: `http://<VM_IP>:8000/health`
   - Should return: `{"status":"healthy",...}`

---

## Optional: Additional Setup

### Option A: PostgreSQL on VM (Recommended for Production)

**If you want database on VM instead of Docker:**

```bash
# 1. Install PostgreSQL
sudo apt-get install -y postgresql-15 postgresql-contrib-15

# 2. Create database and user
sudo -u postgres psql
CREATE DATABASE dataset_studio;
CREATE USER dataset_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE dataset_studio TO dataset_user;
\q

# 3. Configure PostgreSQL to accept connections
sudo nano /etc/postgresql/15/main/postgresql.conf
# Find: listen_addresses = 'localhost'
# Change to: listen_addresses = '*'

sudo nano /etc/postgresql/15/main/pg_hba.conf
# Add: host    dataset_studio    dataset_user    0.0.0.0/0    md5

# 4. Restart PostgreSQL
sudo systemctl restart postgresql

# 5. Update .env file
nano /home/ubuntu/aem-guides-dataset-studio/.env
# Change: DATABASE_URL=postgresql://dataset_user:your_secure_password@localhost:5432/dataset_studio

# 6. Remove PostgreSQL from docker-compose.yml (optional)
# Comment out postgres service

# 7. Restart backend
docker compose restart backend
```

---

### Option B: Auto-Start on VM Reboot

**Services already auto-start** because Docker Compose uses `restart: unless-stopped`.

**To verify:**
```bash
# Reboot VM
sudo reboot

# After reboot, check services
docker compose ps
# All should be running
```

**Optional: Create systemd service** (if needed):
```bash
# See vm-backend.service file for example
```

---

### Option C: SSL/HTTPS Setup (Optional)

**For production, set up HTTPS:**

1. **Install Certbot:**
```bash
sudo apt-get install -y certbot python3-certbot-nginx
```

2. **Get SSL certificate:**
```bash
sudo certbot --nginx -d your-domain.com
```

3. **Update Nginx config** in frontend Dockerfile or use reverse proxy

---

## Quick Setup Script (All-in-One)

**If you want to do everything automatically:**

```bash
# On VM
cd /home/ubuntu/aem-guides-dataset-studio

# Make setup script executable
chmod +x ubuntu-vm-setup.sh

# Run setup (does everything)
sudo bash ubuntu-vm-setup.sh
```

**This script does:**
- ✅ Installs Docker (if not installed)
- ✅ Creates .env file
- ✅ Creates storage directory
- ✅ Configures firewall
- ✅ Builds Docker images
- ✅ Starts all services
- ✅ Verifies everything works

---

## Verification Checklist

After setup, verify everything:

- [ ] Docker is installed: `docker --version`
- [ ] Docker Compose works: `docker compose version`
- [ ] All containers running: `docker compose ps`
- [ ] Backend health check: `curl http://localhost:8000/health`
- [ ] Frontend accessible: `curl http://localhost/`
- [ ] Database connected: Check backend logs
- [ ] Storage directory exists: `ls -ld /home/ubuntu/datasets`
- [ ] Firewall configured: `sudo ufw status`
- [ ] Can access from browser: `http://<VM_IP>/`
- [ ] Can create test dataset: Try creating a small dataset
- [ ] Can download dataset: Verify download works

---

## Common Issues & Solutions

### Issue 1: Port Already in Use

```bash
# Check what's using the port
sudo lsof -i :8000
sudo lsof -i :80

# Stop conflicting service or change port in .env
```

### Issue 2: Permission Denied

```bash
# Add user to docker group
sudo usermod -aG docker ubuntu

# Log out and back in, or:
newgrp docker
```

### Issue 3: Database Connection Failed

```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check logs
docker compose logs postgres

# Test connection
docker compose exec postgres pg_isready -U postgres
```

### Issue 4: Can't Access from Browser

```bash
# 1. Check VM IP
hostname -I

# 2. Check firewall
sudo ufw status

# 3. Check services
docker compose ps

# 4. Test locally first
curl http://localhost:8000/health
```

### Issue 5: Storage Permission Denied

```bash
# Fix permissions
sudo chown -R ubuntu:ubuntu /home/ubuntu/datasets
sudo chmod 755 /home/ubuntu/datasets
```

---

## Post-Setup: First Test

**After everything is setup:**

1. **Open Frontend**: `http://<VM_IP>/`
2. **Create Test Dataset**:
   - Select "Task Topics" recipe
   - Set topic count to 10
   - Click "Create Dataset"
3. **Monitor Progress**: Check Job History page
4. **Download Dataset**: Once completed, download and verify

---

## Summary: What You Need to Setup

### Required:
1. ✅ **Copy project files** to VM
2. ✅ **Create .env file** (environment configuration)
3. ✅ **Create storage directory** (`/home/ubuntu/datasets`)
4. ✅ **Configure firewall** (ports 22, 80, 8000)
5. ✅ **Build Docker images** (`docker compose build`)
6. ✅ **Start services** (`docker compose up -d`)
7. ✅ **Verify services** (health checks, logs)

### Optional (Recommended):
8. ⚠️ **Change PostgreSQL password** (security)
9. ⚠️ **Move database to VM** (production best practice)
10. ⚠️ **Set up SSL/HTTPS** (production)

### Automated:
- **Use `ubuntu-vm-setup.sh`** - Does steps 1-7 automatically!

---

## Quick Reference Commands

```bash
# Start services
cd /home/ubuntu/aem-guides-dataset-studio
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f backend
docker compose logs -f frontend

# Restart services
docker compose restart

# Check status
docker compose ps

# Rebuild after code changes
docker compose build --no-cache
docker compose up -d

# Access backend shell
docker compose exec backend bash

# Access database
docker compose exec postgres psql -U postgres -d dataset_studio
```

---

**Last Updated**: 2026-01-28
