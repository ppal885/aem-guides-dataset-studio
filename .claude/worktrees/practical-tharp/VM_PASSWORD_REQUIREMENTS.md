# VM Password Requirements & Setup

## 🔐 Password Requirements

आपके VM पर password complexity rules हैं:
- ✅ **Minimum 14 characters** (कम से कम 14 characters)
- ✅ **At least 1 uppercase letter** (कम से कम 1 बड़ा अक्षर)
- ✅ **At least 1 non-alphanumeric character** (कम से कम 1 special character: !@#$%^&*)

## 💡 Strong Password Examples

### Option 1: Simple Pattern
```
UbuntuVM2024!@#$
```
- 15 characters ✓
- Uppercase: U ✓
- Special: !@#$ ✓

### Option 2: Memorable Password
```
MyVM@10.42.41.134!
```
- 19 characters ✓
- Uppercase: M ✓
- Special: @.! ✓

### Option 3: Random Strong Password
```
AemGuides2024!@#$%
```
- 18 characters ✓
- Uppercase: A, G ✓
- Special: !@#$% ✓

### Option 4: Easy to Remember
```
UbuntuServer2024!@#
```
- 19 characters ✓
- Uppercase: U, S ✓
- Special: !@# ✓

## 🚀 Quick Password Generator

**PowerShell में:**
```powershell
# Random strong password generate करें
-join ((65..90) + (97..122) + (48..57) + (33..47) | Get-Random -Count 16 | ForEach-Object {[char]$_})
```

**या manually create करें:**
```
Format: [Uppercase][Lowercase][Numbers][Special][Repeat]
Example: UbuntuVM2024!@#$%
```

## 📝 Password Set करने के Steps

### Step 1: Strong Password तैयार करें

**Requirements:**
- Minimum 14 characters
- At least 1 uppercase (A-Z)
- At least 1 lowercase (a-z)
- At least 1 number (0-9)
- At least 1 special character (!@#$%^&*)

**Example:**
```
UbuntuVM2024!@#$
```

### Step 2: VM पर Password Set करें

```bash
# Root user के लिए
passwd root
# New password enter करें (14+ characters, uppercase, special char)

# Ubuntu user के लिए
passwd ubuntu
# New password enter करें
```

### Step 3: Verify करें

```bash
# Logout करें
exit

# नए password से login करें
ssh ubuntu@10.42.41.134
# या
ssh root@10.42.41.134
```

## 🔧 Alternative: SSH Key Setup (Password की जरूरत नहीं)

अगर password complexity से problem है, तो SSH key use करें:

### Step 1: SSH Key Generate करें (Windows पर)

```powershell
# PowerShell में
ssh-keygen -t rsa -b 4096 -C "vm-access"
# Enter press करें (default location के लिए)
# Passphrase skip कर सकते हैं (Enter)
```

### Step 2: Public Key Copy करें

```powershell
# Public key content देखें
cat ~/.ssh/id_rsa.pub
```

### Step 3: VM पर Key Add करें

**Option A: VM Console से (अगर access है)**
```bash
# VM पर login करें
mkdir -p ~/.ssh
nano ~/.ssh/authorized_keys
# Public key paste करें
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

**Option B: Password से Login करके**
```bash
# पहले password से login करें (अगर possible है)
ssh ubuntu@10.42.41.134
# Password enter करें

# फिर key add करें
mkdir -p ~/.ssh
echo "YOUR_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

### Step 4: Password के बिना Connect करें

```powershell
# अब password की जरूरत नहीं
ssh ubuntu@10.42.41.134
```

## 🎯 Recommended Approach

**Best Practice:**
1. Strong password set करें (meets requirements)
2. SSH key setup करें (backup के लिए)
3. Password disable करें (optional, key-based access only)

**Quick Setup:**
```bash
# 1. Strong password set करें
passwd ubuntu
# Enter: UbuntuVM2024!@#$

# 2. SSH key add करें (password से login करके)
mkdir -p ~/.ssh
echo "YOUR_PUBLIC_KEY" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# 3. Test करें
# Password से: ssh ubuntu@10.42.41.134
# Key से: ssh ubuntu@10.42.41.134 (no password)
```

## 📋 Password Examples (Copy-Paste Ready)

```
UbuntuVM2024!@#$
AemGuides2024!@#
MyServer2024!@#$%
UbuntuServer2024!@
VM10.42.41.134!@#
DatasetStudio2024!@#
```

**Note:** इन passwords को use करने से पहले change करें!

## 🆘 Troubleshooting

### Password Still Not Working

```bash
# Password complexity check करें
# Requirements:
# - 14+ characters
# - 1+ uppercase
# - 1+ special character

# Example that works:
UbuntuVM2024!@#$
```

### Can't Remember Password

```bash
# SSH key setup करें (recommended)
# Password के बिना access होगा
```

### Password Reset (Cloud Provider)

**AWS:**
- EC2 Console → Instances → Select VM → Actions → Get Windows Password
- Key pair needed

**Azure:**
- Portal → Virtual Machines → Reset password

**GCP:**
- Console → Compute Engine → Reset password

## ✅ Quick Checklist

- [ ] Password 14+ characters है
- [ ] At least 1 uppercase letter है
- [ ] At least 1 special character है
- [ ] Password successfully set हो गया
- [ ] Login test किया
- [ ] SSH key setup किया (optional but recommended)

---

**Tip:** Strong password set करें और SSH key भी setup करें - दोनों secure और convenient हैं!
