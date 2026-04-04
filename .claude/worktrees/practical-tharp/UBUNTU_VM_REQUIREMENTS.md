# Ubuntu VM Requirements - Applications to Install

## Quick Answer

**Main Requirement:** Only **Docker** and **Docker Compose** need to be installed. Everything else runs in Docker containers.

---

## Required Applications

### 1. **Docker** (CRITICAL)
- **What**: Container runtime
- **Why**: All services (backend, frontend, database) run in Docker containers
- **Version**: Docker Engine 20.10 or later
- **Install**: See installation steps below

### 2. **Docker Compose** (CRITICAL)
- **What**: Multi-container orchestration tool
- **Why**: Manages all services together (backend, frontend, PostgreSQL, Redis)
- **Version**: Docker Compose 2.0 or later
- **Install**: Usually included with Docker, or install separately

### 3. **Essential System Tools** (Recommended)
- `curl` - Download files and test APIs
- `wget` - Download files
- `git` - Clone repositories (if using Git)
- `vim` or `nano` - Text editor for configuration
- `net-tools` - Network utilities (`netstat`, `ifconfig`)
- `ufw` - Firewall management

---

## What Runs in Docker (No Installation Needed)

These run **inside Docker containers** - you don't need to install them separately:

- ✅ **PostgreSQL** - Database (runs in Docker container)
- ✅ **Redis** - Cache/Queue (runs in Docker container)
- ✅ **Python 3.11** - Backend runtime (in Docker image)
- ✅ **Node.js 18+** - Frontend build (in Docker image)
- ✅ **Nginx** - Web server for frontend (in Docker image)
- ✅ **FastAPI/Uvicorn** - Backend server (in Docker image)

---

## Installation Methods

### Option 1: Automated Setup (Recommended)

**Use the provided setup script** - it installs everything automatically:

```bash
# On Ubuntu VM
cd /home/ubuntu/aem-guides-dataset-studio
chmod +x ubuntu-vm-setup.sh
sudo bash ubuntu-vm-setup.sh
```

**What it installs:**
- ✅ Updates system packages
- ✅ Installs Docker and Docker Compose
- ✅ Installs essential tools (curl, wget, git, vim, etc.)
- ✅ Configures firewall
- ✅ Builds Docker images
- ✅ Starts all services

**Time**: 10-15 minutes

---

### Option 2: Manual Installation

If you prefer manual installation:

#### Step 1: Update System
```bash
sudo apt-get update
sudo apt-get upgrade -y
```

#### Step 2: Install Essential Packages
```bash
sudo apt-get install -y \
    curl \
    wget \
    git \
    vim \
    net-tools \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    ufw
```

#### Step 3: Install Docker
```bash
# Remove old versions (if any)
sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Add Docker's GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add user to docker group (so you don't need sudo for docker commands)
sudo usermod -aG docker ubuntu

# Log out and back in for group changes to take effect
# Or run: newgrp docker
```

#### Step 4: Verify Installation
```bash
# Check Docker version
docker --version

# Check Docker Compose version
docker compose version

# Test Docker (should work without sudo after logout/login)
docker run hello-world
```

---

## System Requirements

### Minimum Requirements
- **OS**: Ubuntu 20.04 LTS or later
- **RAM**: 4GB minimum (8GB recommended)
- **Disk Space**: 20GB minimum (50GB recommended for large datasets)
- **CPU**: 2 cores minimum (4 cores recommended)

### Network Requirements
- **Ports to Open**:
  - `22` - SSH (for remote access)
  - `80` - Frontend HTTP
  - `8000` - Backend API
  - `5432` - PostgreSQL (optional, if accessing externally)

---

## Optional: PostgreSQL on VM (Not Required)

**Note**: PostgreSQL runs in Docker by default. You only need to install it on VM if you want to move database out of Docker (as discussed in scalability analysis).

### If Installing PostgreSQL on VM:
```bash
sudo apt-get install -y postgresql-15 postgresql-contrib-15

# Create database
sudo -u postgres psql
CREATE DATABASE dataset_studio;
CREATE USER dataset_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE dataset_studio TO dataset_user;
\q

# Configure firewall
sudo ufw allow 5432/tcp
```

**Then update** `docker-compose.yml`:
```yaml
backend:
  environment:
    DATABASE_URL: postgresql://dataset_user:your_password@VM_IP:5432/dataset_studio
```

---

## Verification Checklist

After installation, verify:

```bash
# 1. Docker is installed
docker --version
# Expected: Docker version 20.10 or later

# 2. Docker Compose is available
docker compose version
# Expected: Docker Compose version 2.0 or later

# 3. Docker daemon is running
sudo systemctl status docker
# Expected: active (running)

# 4. User can run Docker without sudo (after logout/login)
docker ps
# Expected: List of containers (may be empty)

# 5. Essential tools are installed
curl --version
git --version
# Expected: Version numbers
```

---

## Quick Installation Summary

**Minimum Required:**
```bash
# Just Docker and Docker Compose
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo usermod -aG docker $USER
```

**Recommended (Full Setup):**
```bash
# Use automated script
sudo bash ubuntu-vm-setup.sh
```

---

## What You DON'T Need to Install

- ❌ **Python** - Runs in Docker container
- ❌ **Node.js** - Runs in Docker container  
- ❌ **PostgreSQL** - Runs in Docker container (unless you want it on VM)
- ❌ **Redis** - Runs in Docker container
- ❌ **Nginx** - Runs in Docker container
- ❌ **Any application-specific dependencies** - All in Docker

---

## After Installation

Once Docker is installed:

1. **Copy project files** to VM
2. **Run setup script** or manually:
   ```bash
   cd /home/ubuntu/aem-guides-dataset-studio
   docker compose build
   docker compose up -d
   ```

3. **Access application**:
   - Frontend: `http://<VM_IP>/`
   - Backend: `http://<VM_IP>:8000`

---

## Troubleshooting

### Docker Installation Fails
```bash
# Check Ubuntu version
lsb_release -a

# Ensure you have internet connection
ping google.com

# Try manual installation steps above
```

### Permission Denied for Docker
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in, or:
newgrp docker

# Verify
docker ps
```

### Port Already in Use
```bash
# Check what's using the port
sudo lsof -i :8000
sudo lsof -i :80

# Stop conflicting service or change port in .env
```

---

## Summary

**You only need to install:**
1. ✅ **Docker** (container runtime)
2. ✅ **Docker Compose** (orchestration)
3. ✅ **Essential tools** (curl, git, etc. - optional but recommended)

**Everything else runs in Docker containers** - no separate installation needed!

**Easiest way**: Run `sudo bash ubuntu-vm-setup.sh` - it does everything automatically.

---

**Last Updated**: 2026-01-28
