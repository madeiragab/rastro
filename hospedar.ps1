<#
.SYNOPSIS
  Coloca o Rastro no ar usando este PC como servidor.

.DESCRIPTION
  1. Sobe banco + API + site com Docker.
  2. Abre um tunel da Cloudflare: um endereco https://....trycloudflare.com
     publico, que funciona de qualquer rede (4G, Wi-Fi de outro lugar).
     Sem conta e sem abrir porta no roteador.
  3. Gera o APK ja apontando para esse endereco (Rastro-online.apk).

  O PC precisa ficar ligado, com esta janela aberta, enquanto alguem usa.
  O endereco do tunel MUDA cada vez que o script roda -- por isso ele gera o
  APK de novo. Endereco fixo exige conta (ver MANUAL-INSTALACAO.md).

.EXAMPLE
  .\hospedar.ps1            # sobe tudo e gera o APK
  .\hospedar.ps1 -SemApk    # so sobe e abre o tunel
#>
param([switch]$SemApk)

# "Continue": no PowerShell 5.1, redirecionar stderr de programa (docker, npx)
# com "Stop" vira excecao mesmo quando o programa deu certo.
$ErrorActionPreference = "Continue"
$raiz = $PSScriptRoot
Set-Location $raiz

function Passo($texto) { Write-Host "`n==> $texto" -ForegroundColor Green }
function Falha($texto) { Write-Host "`nERRO: $texto" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------ requisitos
Passo "Conferindo programas"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Falha "Docker nao encontrado. Instale com:`n  winget install Docker.DockerDesktop`nreinicie o PC, abra o Docker Desktop e rode este script de novo."
}
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Falha "cloudflared nao encontrado. Instale com:`n  winget install Cloudflare.cloudflared`nfeche e abra o PowerShell e rode este script de novo."
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { Falha "O Docker esta instalado mas nao esta rodando. Abra o Docker Desktop e espere ficar verde." }

# ------------------------------------------------------------ servidor
Passo "Subindo banco, API e site (a primeira vez demora alguns minutos)"
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Falha "docker compose falhou. Veja: docker compose logs" }

Passo "Esperando o site responder em http://localhost:5173"
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
    try {
        $r = Invoke-WebRequest "http://localhost:5173/api/auth/modo" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if (-not $ok) { Falha "O site nao respondeu em 3 minutos. Veja: docker compose logs api web" }

$acesso = docker compose logs api 2>$null | Select-String -Context 0,12 "ACESSO INICIAL"
if ($acesso) {
    Passo "Login inicial (guarde!)"
    $acesso | ForEach-Object { $_.Context.PostContext | Where-Object { $_ -match "e-mail|senha" } | ForEach-Object { ($_ -replace "^.*\|\s*", "") } }
} else {
    Write-Host "(o bloco ACESSO INICIAL so aparece na primeira subida; se perdeu, veja o manual, secao 3.2)"
}

# ------------------------------------------------------------ tunel
Passo "Abrindo tunel publico da Cloudflare"
$log = Join-Path $env:TEMP "rastro-tunel.log"
Remove-Item $log -ErrorAction SilentlyContinue
$tunel = Start-Process cloudflared -ArgumentList "tunnel", "--url", "http://localhost:5173", "--no-autoupdate" `
    -RedirectStandardError $log -NoNewWindow -PassThru

$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
        $achado = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
        if ($achado) { $url = $achado.Matches[0].Value }
    }
}
if (-not $url) { Stop-Process $tunel -ErrorAction SilentlyContinue; Falha "O tunel nao abriu. Veja $log" }
Set-Content -Path (Join-Path $raiz "endereco-publico.txt") -Value $url -Encoding utf8

# A Cloudflare leva alguns segundos para o nome novo valer.
for ($i = 0; $i -lt 30; $i++) {
    try { if ((Invoke-WebRequest "$url/api/auth/modo" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200) { break } } catch { }
    Start-Sleep -Seconds 2
}
Write-Host "No ar em: $url" -ForegroundColor Cyan

# ------------------------------------------------------------ APK
if (-not $SemApk) {
    Passo "Gerando o APK apontando para $url"
    Push-Location (Join-Path $raiz "frontend")
    try {
        if (-not (Test-Path node_modules)) { npm install; if ($LASTEXITCODE -ne 0) { throw "npm install falhou" } }
        npm run build; if ($LASTEXITCODE -ne 0) { throw "npm run build falhou" }
        $env:RASTRO_DEV_URL = $url
        npx cap sync android; if ($LASTEXITCODE -ne 0) { throw "cap sync falhou" }
        Push-Location android
        $tarefa = if (Test-Path keystore.properties) { "assembleRelease" } else { "assembleDebug" }
        .\gradlew.bat $tarefa --console=plain; $codigo = $LASTEXITCODE
        Pop-Location
        if ($codigo -ne 0) { throw "gradle falhou (veja MANUAL-INSTALACAO.md, erros do Android)" }
        $tipo = if ($tarefa -eq "assembleRelease") { "release\app-release.apk" } else { "debug\app-debug.apk" }
        Copy-Item "android\app\build\outputs\apk\$tipo" (Join-Path $raiz "Rastro-online.apk") -Force
        Write-Host "APK pronto: $(Join-Path $raiz 'Rastro-online.apk')" -ForegroundColor Cyan
    } catch {
        Write-Host "Nao deu para gerar o APK: $_" -ForegroundColor Yellow
        Write-Host "O site continua no ar; no celular, abra $url no navegador."
    } finally {
        # Volta o projeto Android ao normal, sem endereco fixo.
        Remove-Item Env:RASTRO_DEV_URL -ErrorAction SilentlyContinue
        npx cap sync android *> $null
        Pop-Location
    }
}

# ------------------------------------------------------------ pronto
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " RASTRO NO AR: $url"
Write-Host " - No celular: instale o Rastro-online.apk ou abra o endereco no navegador."
Write-Host " - Mantenha o PC ligado e ESTA JANELA ABERTA."
Write-Host " - Ctrl+C derruba o tunel. Para desligar tudo: docker compose down"
Write-Host "============================================================" -ForegroundColor Green

try { Wait-Process -Id $tunel.Id } finally { Stop-Process $tunel -ErrorAction SilentlyContinue }
