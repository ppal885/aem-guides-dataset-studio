# VM Setup - Next Steps (SSH Key से Login हो गया)

## ✅ Current Status
- ✓ SSH key setup complete
- ✓ VM में login हो गया
- ⏭️ अब project setup करना है

## 🚀 Step-by-Step Setup

### Step 1: Project Files Copy करें

**Windows PowerShell से (नया terminal खोलें):**

```powershell
# Project directory में जाएं
cd C:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio

# Files copy करें
scp -r . ubuntu@10.42.41.134:/home/ubuntu/aem-guides-dataset-studio
```

**या PowerShell script use करें:**
```powershell
.\copy-to-vm.ps1
```

**या Git से (अगर repo है):**
```bash
# VM पर (जहाँ आप login हैं)
cd /home/ubuntu
git clone <your-repo-url> aem-guides-dataset-studio
```

### Step 2: VM पर Setup Run करें

**VM terminal में (जहाँ आप login हैं):**

```bash
# Project directory में जाएं
cd /home/ubuntu/aem-guides-dataset-studio

# Check करें files आ गए हैं
ls -la

# Setup script को executable बनाएं
chmod +x ubuntu-vm-setup.sh

# Setup run करें (sudo जरूरी है)
sudo bash ubuntu-vm-setup.sh
```

### Step 3: Wait करें

Setup script automatically करेगा:
- ✅ System update
- ✅ Docker install
- ✅ Dependencies install
- ✅ Environment configure
- ✅ Services start

**Time:** 10-15 minutes

### Step 4: Verify करें

```bash
# Verification script run करें
bash vm-verify-setup.sh

# या manually check करें
docker compose ps
curl http://localhost:8000/health
```

## 📋 Quick Commands (VM पर)

```bash
# Current directory check
pwd

# Files check करें
ls -la

# Project directory में जाएं
cd /home/ubuntu/aem-guides-dataset-studio

# Setup run करें
chmod +x ubuntu-vm-setup.sh
sudo bash ubuntu-vm-setup.sh
```

## 🔍 Check करें Files आ गए हैं

```bash
# VM पर
ls -la /home/ubuntu/aem-guides-dataset-studio

# ये files दिखनी चाहिए:
# - docker-compose.yml
# - ubuntu-vm-setup.sh
# - backend/
# - frontend/
# - etc.
```

## 🆘 अगर Files नहीं आए

**Windows PowerShell से फिर से copy करें:**
```powershell
cd C:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio
scp -r . ubuntu@10.42.41.134:/home/ubuntu/aem-guides-dataset-studio
```

**या Git clone करें:**
```bash
# VM पर
cd /home/ubuntu
git clone <repo-url> aem-guides-dataset-studio
```

## ✅ Setup Complete के बाद

Access करें:
- **Frontend**: http://10.42.41.134/
- **Backend**: http://10.42.41.134:8000
- **API Docs**: http://10.42.41.134:8000/docs

## 📝 Complete Flow

```bash
# VM पर (जहाँ आप login हैं)

# 1. Check current location
pwd

# 2. Project directory check करें
ls -la /home/ubuntu/aem-guides-dataset-studio

# 3. अगर files नहीं हैं, Windows से copy करें
# (नया PowerShell window खोलें)

# 4. Project directory में जाएं
cd /home/ubuntu/aem-guides-dataset-studio

# 5. Setup run करें
chmod +x ubuntu-vm-setup.sh
sudo bash ubuntu-vm-setup.sh

# 6. Wait करें (10-15 minutes)

# 7. Verify करें
bash vm-verify-setup.sh
```

---

**अभी Windows से files copy करें, फिर VM पर setup run करें! 🚀**
