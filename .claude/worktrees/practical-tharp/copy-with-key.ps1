# Copy Files to VM Using SSH Key (No Password)
# Usage: .\copy-with-key.ps1

$VM_IP = "10.42.41.134"
$VM_USER = "ubuntu"
$VM_PATH = "/home/ubuntu/aem-guides-dataset-studio"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Copying Files to VM (Using SSH Key)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Find SSH key
$sshKeyPath = "$env:USERPROFILE\.ssh\id_rsa"
$sshKeyEd25519Path = "$env:USERPROFILE\.ssh\id_ed25519"
$keyToUse = $null

if (Test-Path $sshKeyEd25519Path) {
    $keyToUse = $sshKeyEd25519Path
    Write-Host "✓ Found SSH key: $keyToUse" -ForegroundColor Green
} elseif (Test-Path $sshKeyPath) {
    $keyToUse = $sshKeyPath
    Write-Host "✓ Found SSH key: $keyToUse" -ForegroundColor Green
} else {
    Write-Host "✗ No SSH key found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "1. Generate SSH key:" -ForegroundColor White
    Write-Host "   ssh-keygen -t rsa -b 4096" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "2. Copy public key to VM:" -ForegroundColor White
    Write-Host "   cat ~/.ssh/id_rsa.pub | ssh ubuntu@$VM_IP 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys'" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "3. Or use password (will be prompted):" -ForegroundColor White
    Write-Host "   scp -r . ubuntu@$VM_IP:$VM_PATH" -ForegroundColor Cyan
    exit 1
}

# Check if we're in the right directory
if (-not (Test-Path "docker-compose.yml")) {
    Write-Host "Error: docker-compose.yml not found!" -ForegroundColor Red
    Write-Host "Please run this script from the project root directory" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Project directory: $(Get-Location)" -ForegroundColor Green
Write-Host "VM IP: $VM_IP" -ForegroundColor Green
Write-Host "VM Path: $VM_PATH" -ForegroundColor Green
Write-Host "SSH Key: $keyToUse" -ForegroundColor Green
Write-Host ""

# Test SSH connection
Write-Host "Testing SSH connection..." -ForegroundColor Yellow
try {
    if ($keyToUse) {
        $testResult = ssh -i $keyToUse -o ConnectTimeout=5 -o BatchMode=yes "$VM_USER@$VM_IP" "echo 'Connection successful'" 2>&1
    } else {
        $testResult = ssh -o ConnectTimeout=5 -o BatchMode=yes "$VM_USER@$VM_IP" "echo 'Connection successful'" 2>&1
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ SSH connection successful!" -ForegroundColor Green
    } else {
        Write-Host "⚠ SSH connection test failed" -ForegroundColor Yellow
        Write-Host "  Will try anyway..." -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠ SSH connection test failed: $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Copying files to VM..." -ForegroundColor Yellow
Write-Host "This may take a few minutes..." -ForegroundColor Yellow
Write-Host ""

# Create directory on VM
Write-Host "Creating directory on VM..." -ForegroundColor Yellow
if ($keyToUse) {
    ssh -i $keyToUse "$VM_USER@$VM_IP" "mkdir -p $VM_PATH" 2>&1 | Out-Null
} else {
    ssh "$VM_USER@$VM_IP" "mkdir -p $VM_PATH" 2>&1 | Out-Null
}

# Copy files using SCP with key
Write-Host "Copying files..." -ForegroundColor Yellow
if ($keyToUse) {
    scp -i $keyToUse -r . "$VM_USER@${VM_IP}:$VM_PATH"
} else {
    scp -r . "$VM_USER@${VM_IP}:$VM_PATH"
}

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Files copied successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. SSH into VM: ssh -i $keyToUse $VM_USER@$VM_IP" -ForegroundColor Yellow
    Write-Host "2. Navigate: cd $VM_PATH" -ForegroundColor Yellow
    Write-Host "3. Run setup: chmod +x ubuntu-vm-setup.sh && sudo bash ubuntu-vm-setup.sh" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Copy failed! Exit code: $LASTEXITCODE" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "1. Check SSH key permissions" -ForegroundColor White
    Write-Host "2. Verify key is added to VM: ssh -i $keyToUse $VM_USER@$VM_IP" -ForegroundColor White
    Write-Host "3. Try manual copy: scp -i $keyToUse -r . $VM_USER@${VM_IP}:$VM_PATH" -ForegroundColor White
    exit 1
}
