$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if ($env:OS -ne "Windows_NT") { throw "Execute este script no Windows." }
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Comando falhou com código ${LASTEXITCODE}: $Program" }
}
if (!(Test-Path ".venv\Scripts\python.exe")) {
    Invoke-Checked "py" @("-3.12", "-m", "venv", ".venv")
}
$Python = (Resolve-Path ".venv\Scripts\python.exe").Path
Invoke-Checked $Python @("-m", "pip", "install", "-r", "requirements-dev.txt")
$env:QT_QPA_PLATFORM = "offscreen"
Invoke-Checked $Python @("-m", "pytest", "-q")
Remove-Item Env:QT_QPA_PLATFORM
Invoke-Checked $Python @("-m", "PyInstaller", "--noconfirm", "--clean", "HilfPrint.spec")
Invoke-Checked ".\dist\HilfPrint\HilfPrint.exe" @("--smoke-test")
Compress-Archive -Path "dist\HilfPrint" -DestinationPath "dist\HilfPrint-Windows.zip" -Force
Write-Host "Entrega portátil: dist\HilfPrint\HilfPrint.exe e dist\HilfPrint-Windows.zip"
Write-Host "Copie a pasta inteira. Valide abertura, arraste, PDFs reais e impressão antes de uso operacional."
