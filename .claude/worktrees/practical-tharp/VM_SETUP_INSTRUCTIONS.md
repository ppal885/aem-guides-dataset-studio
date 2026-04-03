# Ubuntu VM Setup Instructions

## 📋 What You Need

1. **Ubuntu VM** (20.04 LTS or later) with:
   - SSH access
   - Sudo privileges
   - At least 4GB RAM, 20GB disk space

2. **VM IP Address** - You'll need this to connect

3. **Project Files** - Already in this directory

## 🚀 Setup Steps

### Step 1: Copy Files to VM

**Option A: Using SCP (from Windows PowerShell)**
```powershell
# Navigate to project directory
cd C:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio

# Copy entire project to VM
scp -r . ubuntu@<VM_IP>:/home/ubuntu/aem-guides-dataset-studio
```

**Option B: Using Git (if you have a repository)**
```bash
ssh ubuntu@<VM_IP>
cd /home/ubuntu
git clone <your-repo-url> aem-guides-dataset-studio
```

**Option C: Using rsync (if available)**
```bash
rsync -avz --exclude 'node_modules' --exclude '__pycache__' --exclude '.git' \
  ./ ubuntu@<VM_IP>:/home/ubuntu/aem-guides-dataset-studio/
```

### Step 2: Run Setup Script

```bash
# SSH into VM
ssh ubuntu@<VM_IP>

# Navigate to project
cd /home/ubuntu/aem-guides-dataset-studio

# Make script executable
chmod +x ubuntu-vm-setup.sh

# Run setup (requires sudo)
sudo bash ubuntu-vm-setup.sh
```

The setup script will:
- ✅ Install Docker and Docker Compose
- ✅ Install all required dependencies
- ✅ Configure environment variables
- ✅ Set up firewall rules
- ✅ Build Docker images
- ✅ Start all services
- ✅ Verify everything is working

**Time Required:** 10-15 minutes (depending on internet speed)

### Step 3: Verify Setup

After setup completes, verify everything is working:

```bash
# Run verification script
bash vm-verify-setup.sh

# Or manually check
docker compose ps
curl http://localhost:8000/health
```

### Step 4: Access Your Application

Find your VM IP:
```bash
hostname -I
```

Then access:
- **Frontend**: `http://<VM_IP>/`
- **Backend API**: `http://<VM_IP>:8000`
- **API Docs**: `http://<VM_IP>:8000/docs`

## 📝 What Gets Installed

- **Docker** - Container runtime
- **Docker Compose** - Multi-container orchestration
- **PostgreSQL** - Database (in Docker container)
- **Redis** - Cache/Queue (in Docker container)
- **Python Backend** - FastAPI application (in Docker container)
- **Node.js Frontend** - React application (in Docker container)

## 🔧 Post-Setup Configuration

### Update Environment Variables (Optional)

Edit `.env` file if needed:
```bash
nano /home/ubuntu/aem-guides-dataset-studio/.env
```

Key settings:
- `STORAGE_PATH=/home/ubuntu/datasets` - Where datasets are stored
- `POSTGRES_PASSWORD=postgres` - Change this for security
- `BACKEND_PORT=8000` - Backend API port
- `FRONTEND_PORT=80` - Frontend port

### Configure Firewall

If firewall is enabled, ensure ports are open:
```bash
sudo ufw allow 80/tcp    # Frontend
sudo ufw allow 8000/tcp  # Backend
sudo ufw status
```

## 📚 Documentation Files

- **UBUNTU_VM_SETUP_GUIDE.md** - Complete detailed guide
- **VM_QUICK_REFERENCE.md** - Quick command reference
- **DATASET_GENERATOR_USAGE_GUIDE.md** - How to use the application

## 🆘 Troubleshooting

### Setup Script Fails

1. Check internet connection on VM
2. Ensure you have sudo privileges
3. Check logs: The script will show errors

### Services Not Starting

```bash
# Check container status
docker compose ps

# View logs
docker compose logs

# Restart services
docker compose restart
```

### Can't Access from Browser

1. Check VM IP: `hostname -I`
2. Check firewall: `sudo ufw status`
3. Check services: `docker compose ps`
4. Test locally: `curl http://localhost:8000/health`

### Port Already in Use

```bash
# Find what's using the port
sudo lsof -i :8000
sudo lsof -i :80

# Stop conflicting service or change port in .env
```

## 🔄 Updating the Application

When you make code changes:

```bash
# On VM
cd /home/ubuntu/aem-guides-dataset-studio

# Pull latest code (if using git)
git pull

# Rebuild and restart
docker compose down
docker compose build --no-cache
docker compose up -d
```

## ✅ Verification Checklist

After setup, verify:

- [ ] Docker is installed and running
- [ ] All containers are running (`docker compose ps`)
- [ ] Backend health check works (`curl http://localhost:8000/health`)
- [ ] Frontend is accessible (`curl http://localhost/`)
- [ ] Can access from browser using VM IP
- [ ] Firewall allows necessary ports
- [ ] Storage directory exists (`/home/ubuntu/datasets`)

## 🎯 Next Steps

1. **Test the Application**
   - Open frontend in browser
   - Create a test dataset
   - Verify it downloads correctly

2. **Configure Auto-Start** (Optional)
   - Services already auto-start with Docker
   - For systemd service, see VM_QUICK_REFERENCE.md

3. **Set Up Monitoring** (Optional)
   - Monitor disk space
   - Set up log rotation
   - Configure alerts

4. **Security Hardening** (Recommended)
   - Change default passwords
   - Set up SSL/HTTPS
   - Configure proper firewall rules
   - Regular security updates

## 📞 Need Help?

1. Check logs: `docker compose logs`
2. Run verification: `bash vm-verify-setup.sh`
3. Review troubleshooting section above
4. Check detailed guide: `UBUNTU_VM_SETUP_GUIDE.md`

---

**Ready to deploy? Run the setup script and you're good to go! 🚀**
