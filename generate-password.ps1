# Generate Strong Password for VM
# Usage: .\generate-password.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "VM Password Generator" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Password Requirements:" -ForegroundColor Yellow
Write-Host "  - Minimum 14 characters" -ForegroundColor White
Write-Host "  - At least 1 uppercase letter" -ForegroundColor White
Write-Host "  - At least 1 lowercase letter" -ForegroundColor White
Write-Host "  - At least 1 number" -ForegroundColor White
Write-Host "  - At least 1 special character (!@#`$%^&*)" -ForegroundColor White
Write-Host ""

# Generate random password
function Generate-Password {
    param([int]$Length = 16)
    
    $uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    $lowercase = "abcdefghijklmnopqrstuvwxyz"
    $numbers = "0123456789"
    $special = "!@#$%^&*"
    
    $password = ""
    
    # Ensure at least one of each type
    $password += $uppercase[(Get-Random -Maximum $uppercase.Length)]
    $password += $lowercase[(Get-Random -Maximum $lowercase.Length)]
    $password += $numbers[(Get-Random -Maximum $numbers.Length)]
    $password += $special[(Get-Random -Maximum $special.Length)]
    
    # Fill remaining length
    $allChars = $uppercase + $lowercase + $numbers + $special
    for ($i = $password.Length; $i -lt $Length; $i++) {
        $password += $allChars[(Get-Random -Maximum $allChars.Length)]
    }
    
    # Shuffle the password
    $passwordArray = $password.ToCharArray()
    $shuffled = $passwordArray | Get-Random -Count $passwordArray.Length
    return -join $shuffled
}

# Generate multiple password options
Write-Host "Generated Password Options:" -ForegroundColor Green
Write-Host ""

for ($i = 1; $i -le 5; $i++) {
    $pwd = Generate-Password -Length 16
    Write-Host "Option $i`: $pwd" -ForegroundColor Cyan
}

Write-Host ""

# Generate memorable password
Write-Host "Memorable Password Options:" -ForegroundColor Green
Write-Host ""

$memorablePasswords = @(
    "UbuntuVM2024!@#`$",
    "AemGuides2024!@#",
    "MyVM@10.42.41.134!",
    "DatasetStudio2024!@#",
    "UbuntuServer2024!@#"
)

foreach ($pwd in $memorablePasswords) {
    Write-Host "  $pwd" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Instructions:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Copy one of the passwords above" -ForegroundColor White
Write-Host "2. On VM, run: passwd ubuntu" -ForegroundColor White
Write-Host "3. Paste the password when prompted" -ForegroundColor White
Write-Host "4. Confirm the password" -ForegroundColor White
Write-Host ""
Write-Host "Or use SSH key (recommended):" -ForegroundColor Yellow
Write-Host "  ssh-keygen -t rsa -b 4096" -ForegroundColor Cyan
Write-Host "  ssh-copy-id ubuntu@10.42.41.134" -ForegroundColor Cyan
Write-Host ""
