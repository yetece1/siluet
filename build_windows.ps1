$ErrorActionPreference = "Stop"

# Windows PowerShell 5.1'de "Stop" harici programların hata kodlarını yakalamaz; her çağrı denetlenir.
function Invoke-Checked {
    param([string]$Step, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Step başarısız oldu (çıkış kodu $LASTEXITCODE); paket üretilmedi." }
}
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildDir = Join-Path $ProjectDir "build\windows"
$DistDir = Join-Path $ProjectDir "dist"
$Venv = Join-Path $BuildDir "venv"
# Python 3.10 veya üstü gerekir; PYTHON_LAUNCHER ile başka sürüm seçilebilir (ör. "-3.12").
$PyVersion = if ($env:PYTHON_LAUNCHER) { $env:PYTHON_LAUNCHER } else { "-3" }
Invoke-Checked "Sanal ortam" { py $PyVersion -m venv $Venv }
Invoke-Checked "pip güncelleme" { & "$Venv\Scripts\python.exe" -m pip install --upgrade pip }
Invoke-Checked "Bağımlılık kurulumu" { & "$Venv\Scripts\python.exe" -m pip install "pyinstaller>=6,<7" -r "$ProjectDir\requirements.txt" }
$env:QT_QPA_PLATFORM = "offscreen"
Invoke-Checked "Testler" { & "$Venv\Scripts\python.exe" -m pytest -q "$ProjectDir\tests" -p no:cacheprovider }
Remove-Item Env:\QT_QPA_PLATFORM
Invoke-Checked "Derleme" {
  & "$Venv\Scripts\pyinstaller.exe" --noconfirm --clean --distpath $DistDir --workpath "$BuildDir\work" `
    "$ProjectDir\packaging\siluet.spec"
}
Copy-Item "$ProjectDir\packaging\windows\KURULUM.txt" "$DistDir\Siluet\"
Copy-Item "$ProjectDir\LICENSE" "$DistDir\Siluet\LICENSE.txt"
Compress-Archive -Path "$DistDir\Siluet" -DestinationPath "$DistDir\Siluet-windows.zip" -Force

Write-Host "Derleme tamamlandı: $DistDir\Siluet-windows.zip"
