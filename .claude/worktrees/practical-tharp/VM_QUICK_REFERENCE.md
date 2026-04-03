# VM Quick Reference Card

## 🚀 Quick Start

```bash
# 1. Copy files to VM
scp -r ./aem-guides-dataset-studio ubuntu@<VM_IP>:/home/ubuntu/

# 2. SSH into VM
ssh ubuntu@<VM_IP>

# 3. Run setup
cd /home/ubuntu/aem-guides-dataset-studio
chmod +x ubuntu-vm-setup.sh
sudo bash ubuntu-vm-setup.sh

# 4. Verify
bash vm-verify-setup.sh
```

## 📍 Access URLs

Replace `<VM_IP>` with your VM's IP (`hostname -I`)

- Frontend: `http://<VM_IP>/`
- Backend: `http://<VM_IP>:8000`
- API Docs: `http://<VM_IP>:8000/docs`
- Health: `http://<VM_IP>:8000/health`

## 🔧 Common Commands

```bash
cd /home/ubuntu/aem-guides-dataset-studio

# Start services
docker compose up -d

# Stop services
docker compose down

# Restart services
docker compose restart

# View logs
docker compose logs -f

# Check status
docker compose ps

# View backend logs only
docker compose logs -f backend

# View frontend logs only
docker compose logs -f frontend
```

## 🔍 Troubleshooting

```bash
# Check if services are running
docker compose ps

# Check backend health
curl http://localhost:8000/health

# Check database
docker compose exec postgres pg_isready -U postgres

# View all logs
docker compose logs --tail=100

# Restart everything
docker compose down && docker compose up -d
```

## 📦 Update Application

```bash
cd /home/ubuntu/aem-guides-dataset-studio
git pull
docker compose down
docker compose build --no-cache
docker compose up -d
```

## 💾 Backup

```bash
# Backup database
docker compose exec postgres pg_dump -U postgres dataset_studio > backup-$(date +%Y%m%d).sql

# Backup datasets
tar -czf datasets-$(date +%Y%m%d).tar.gz /home/ubuntu/datasets
```

## 🔐 Security

```bash
# Check firewall
sudo ufw status

# Open ports
sudo ufw allow 80/tcp
sudo ufw allow 8000/tcp
```

## 📊 Monitoring

```bash
# Resource usage
docker stats

# Disk space
df -h
du -sh /home/ubuntu/datasets

# Container logs
docker compose logs --tail=50
```

## 🆘 Emergency Commands

```bash
# Stop everything
docker compose down

# Remove all containers and volumes (⚠️ deletes data)
docker compose down -v

# Clean Docker system
docker system prune -a

# Check what's using ports
sudo lsof -i :8000
sudo lsof -i :80
```

## 📝 File Locations

- Project: `/home/ubuntu/aem-guides-dataset-studio`
- Datasets: `/home/ubuntu/datasets`
- Logs: `docker compose logs`
- Config: `/home/ubuntu/aem-guides-dataset-studio/.env`

## 🔄 Auto-Start Setup

```bash
# Create systemd service
sudo nano /etc/systemd/system/dataset-studio.service

# Add:
[Unit]
Description=AEM Guides Dataset Studio
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ubuntu/aem-guides-dataset-studio
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=ubuntu

[Install]
WantedBy=multi-user.target

# Enable
sudo systemctl daemon-reload
sudo systemctl enable dataset-studio
sudo systemctl start dataset-studio
```

---

**Keep this handy for quick reference! 📌**
