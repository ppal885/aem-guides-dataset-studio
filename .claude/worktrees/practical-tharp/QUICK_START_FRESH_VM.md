# 🚀 Fresh VM Quick Start (हिंदी में)

## सिर्फ 3 Steps!

### Step 1: Files Copy करें (Windows से)

**PowerShell में:**
```powershell
cd C:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio
scp -r . ubuntu@<VM_IP>:/home/ubuntu/aem-guides-dataset-studio
```

### Step 2: VM पर Setup Run करें

```bash
ssh ubuntu@<VM_IP>
cd /home/ubuntu/aem-guides-dataset-studio
chmod +x ubuntu-vm-setup.sh
sudo bash ubuntu-vm-setup.sh
```

### Step 3: Wait करें और Verify करें

```bash
# 10-15 minutes wait करें
# फिर verify करें:
bash vm-verify-setup.sh
```

## ✅ हो गया!

अब access करें:
- Frontend: `http://<VM_IP>/`
- Backend: `http://<VM_IP>:8000`
- API Docs: `http://<VM_IP>:8000/docs`

## 📝 Important

- ✅ Script automatically सब कुछ install करेगा
- ✅ Docker, dependencies, सब कुछ fresh install होगा
- ✅ Internet connection जरूरी है
- ✅ 10-15 minutes लगेंगे

## 🆘 Problem?

```bash
# Logs देखें
cd /home/ubuntu/aem-guides-dataset-studio
docker compose logs

# Status check
docker compose ps
```

**बस इतना ही! Script बाकी सब handle करेगा! 🎯**
