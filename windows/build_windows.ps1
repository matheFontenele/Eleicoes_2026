[CmdletBinding()]
param(
    [switch]$BuildInstaller
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot
$BuildVenv = Join-Path $ProjectRoot ".venv-build"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher (py.exe) com Python 3.12 é necessário para o build."
}
$PythonVersion = & py -3.12 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $PythonVersion.Trim() -ne "3.12") {
    throw "Este build requer Python 3.12; encontrado: $PythonVersion"
}

# Start from a clean build environment/output so the result is reproducible.
if (Test-Path $BuildVenv) { Remove-Item -Recurse -Force $BuildVenv }
if (Test-Path (Join-Path $ProjectRoot "build")) { Remove-Item -Recurse -Force (Join-Path $ProjectRoot "build") }
if (Test-Path (Join-Path $ProjectRoot "dist")) { Remove-Item -Recurse -Force (Join-Path $ProjectRoot "dist") }
& py -3.12 -m venv $BuildVenv
if ($LASTEXITCODE -ne 0) { throw "Falha ao criar ambiente virtual de build." }
$Python = Join-Path $BuildVenv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Falha ao atualizar pip." }
& $Python -m pip install -r (Join-Path $ProjectRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar dependências do build." }
& $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $ProjectRoot "dist") `
    --workpath (Join-Path $ProjectRoot "build\pyinstaller") `
    (Join-Path $ProjectRoot "CE2026Dashboard.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

$BundledData = Join-Path $ProjectRoot "dist\CE2026Dashboard\_internal\data\ce_votos.parquet"
if (-not (Test-Path $BundledData)) {
    throw "Parquet não foi incluído no pacote: $BundledData"
}
Write-Host "Build onedir pronto em dist\CE2026Dashboard"

if ($BuildInstaller) {
    $Iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    $IsccPath = if ($Iscc) { $Iscc.Source } else { $null }
    if (-not $IsccPath) {
        $CommonIsccPaths = @(
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 5\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 5\ISCC.exe")
        )
        $IsccPath = $CommonIsccPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $IsccPath) { throw "ISCC.exe não encontrado no PATH nem nos caminhos comuns de instalação do Inno Setup." }
    & $IsccPath (Join-Path $ProjectRoot "windows\installer.iss")
    if ($LASTEXITCODE -ne 0) { throw "Compilação do instalador Inno Setup falhou." }
    Write-Host "Instalador criado em dist\installer"
}
