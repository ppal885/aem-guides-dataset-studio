# Linux VM Dev Runbook

Use this when you want to pull latest code on the VM and run backend + frontend without Docker.

## Start

```bash
cd ~/aem-guides-dataset-studio
git pull origin main
chmod +x start-vm-dev.sh
bash start-vm-dev.sh
```

If an old backend/frontend process is already using the ports:

```bash
bash start-vm-dev.sh --kill-ports
```

Default ports:

- Backend: `8001`
- Frontend: `5173`

Open:

```text
http://<VM-IP>:5173
```

## If backend must run on 8000

```bash
bash start-vm-dev.sh --backend-port 8000 --frontend-port 5173
```

The script writes `frontend/.env` automatically:

```env
VITE_PROXY_TARGET=http://127.0.0.1:<backend-port>
```

## Stop

```bash
cd ~/aem-guides-dataset-studio
bash start-vm-dev.sh --stop
```

## Logs

```bash
tail -f logs/backend-vm-dev.log
tail -f logs/frontend-vm-dev.log
```

## Common checks

```bash
lsof -i :5173
lsof -i :8001
curl http://127.0.0.1:5173
curl http://127.0.0.1:8001/health
```

If `npm not found`, install Node.js 20 LTS:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

If `python3-venv` is missing:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

If Ubuntu asks for the version-specific package:

```bash
sudo apt install -y python3.10-venv python3-pip
```
