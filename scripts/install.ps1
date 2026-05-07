$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$BinDir = Join-Path $Root "bin"
$DownloadDir = Join-Path $BinDir "_downloads"
$Requirements = Join-Path $Root "requirements.txt"
$PythonSeries = "3.13"
$GyanFfmpegApi = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
$GyanFfmpegFallbackUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Download($Uri, $OutFile) {
    Write-Host "Downloading: $Uri"

    $outDir = Split-Path -Parent $OutFile
    if ($outDir -and -not (Test-Path -LiteralPath $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }

    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        & curl.exe --location --fail --retry 5 --retry-delay 2 --connect-timeout 30 --output "$OutFile" "$Uri"
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $OutFile)) {
            return
        }
        Write-Host "curl.exe download failed, trying PowerShell fallback..." -ForegroundColor Yellow
    }

    try {
        Start-BitsTransfer -Source $Uri -Destination $OutFile -DisplayName "LUT Studio download" -Description $Uri -ErrorAction Stop
        if (Test-Path -LiteralPath $OutFile) {
            return
        }
    } catch {
        Write-Host "BITS download failed, trying Invoke-WebRequest fallback..." -ForegroundColor Yellow
    }

    Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UseBasicParsing
}

function Get-LatestPythonEmbed {
    Write-Step "Finding latest Python $PythonSeries embeddable runtime"

    $index = Invoke-WebRequest -Uri "https://www.python.org/ftp/python/" -UseBasicParsing
    $pattern = 'href="(' + [regex]::Escape($PythonSeries) + '\.\d+)/"'
    $versions = [regex]::Matches($index.Content, $pattern) |
        ForEach-Object { $_.Groups[1].Value } |
        Sort-Object -Property { [version]$_ } -Descending

    foreach ($version in $versions) {
        $url = "https://www.python.org/ftp/python/$version/python-$version-embed-amd64.zip"
        try {
            $request = [System.Net.WebRequest]::Create($url)
            $request.Method = "HEAD"
            $response = $request.GetResponse()
            $response.Close()
            return [pscustomobject]@{
                Version = $version
                Url = $url
            }
        } catch {
            continue
        }
    }

    throw "Could not find a Python $PythonSeries embeddable x64 package."
}

function Get-PortablePython {
    $existing = Get-ChildItem -LiteralPath $BinDir -Directory -Filter "python-*-embed-amd64" -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "python.exe") } |
        Sort-Object Name -Descending |
        Select-Object -First 1

    if ($existing) {
        Write-Step "Using existing portable Python"
        Write-Host $existing.FullName
        return $existing.FullName
    }

    $python = Get-LatestPythonEmbed
    $zipPath = Join-Path $DownloadDir "python-$($python.Version)-embed-amd64.zip"
    $targetDir = Join-Path $BinDir "python-$($python.Version)-embed-amd64"

    Write-Step "Installing Python $($python.Version) embeddable x64"
    Invoke-Download $python.Url $zipPath

    if (Test-Path -LiteralPath $targetDir) {
        Remove-Item -LiteralPath $targetDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $targetDir | Out-Null
    Expand-Archive -LiteralPath $zipPath -DestinationPath $targetDir -Force

    return $targetDir
}

function Enable-PythonSite($PythonDir) {
    Write-Step "Enabling site-packages for embedded Python"

    $pth = Get-ChildItem -LiteralPath $PythonDir -File -Filter "python*._pth" | Select-Object -First 1
    if (-not $pth) {
        throw "Could not find python*._pth in $PythonDir"
    }

    $lines = Get-Content -LiteralPath $pth.FullName
    $updated = @()
    $hasImportSite = $false

    foreach ($line in $lines) {
        if ($line.Trim() -eq "import site") {
            $hasImportSite = $true
            $updated += $line
        } elseif ($line.Trim() -eq "#import site") {
            $hasImportSite = $true
            $updated += "import site"
        } else {
            $updated += $line
        }
    }

    if (-not $hasImportSite) {
        $updated += "import site"
    }

    Set-Content -LiteralPath $pth.FullName -Value $updated -Encoding ASCII
}

function Install-PipAndRequirements($PythonDir) {
    $pythonExe = Join-Path $PythonDir "python.exe"
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw "python.exe was not found in $PythonDir"
    }
    if (-not (Test-Path -LiteralPath $Requirements)) {
        throw "requirements.txt was not found at $Requirements"
    }

    Write-Step "Bootstrapping pip"
    $pipOk = $false
    try {
        & $pythonExe -m pip --version > $null 2>&1
        $pipOk = ($LASTEXITCODE -eq 0)
    } catch {
        $pipOk = $false
    }

    if (-not $pipOk) {
        $getPip = Join-Path $DownloadDir "get-pip.py"
        Invoke-Download "https://bootstrap.pypa.io/get-pip.py" $getPip
        & $pythonExe $getPip --no-warn-script-location
        if ($LASTEXITCODE -ne 0) {
            throw "get-pip.py failed."
        }
    }

    Write-Step "Installing pip packages from requirements.txt"
    & $pythonExe -m pip install --upgrade --no-warn-script-location pip setuptools wheel
    if ($LASTEXITCODE -ne 0) {
        throw "pip upgrade failed."
    }

    & $pythonExe -m pip install --upgrade --prefer-binary --no-warn-script-location -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        throw "requirements install failed."
    }
}

function Install-PortableFfmpeg {
    Write-Step "Installing latest Gyan.dev release FFmpeg"

    $ffmpegDir = Join-Path $BinDir "ffmpeg"
    $zipPath = Join-Path $DownloadDir "ffmpeg-latest-win64.zip"
    $extractDir = Join-Path $DownloadDir "ffmpeg_extract"
    $downloadUrl = $GyanFfmpegFallbackUrl

    try {
        Write-Host "Resolving latest GyanD/codexffmpeg release..."
        $release = Invoke-RestMethod -Uri $GyanFfmpegApi -Headers @{ "User-Agent" = "LUT-Studio-Installer" }
        $asset = $release.assets |
            Where-Object { $_.name -match '^ffmpeg-.+-essentials_build\.zip$' } |
            Select-Object -First 1

        if ($asset -and $asset.browser_download_url) {
            $downloadUrl = $asset.browser_download_url
            Write-Host "Latest release: $($release.tag_name) / $($asset.name)"
        } else {
            Write-Host "Could not find essentials ZIP asset in GitHub API response; using gyan.dev fallback." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Could not resolve GitHub release; using gyan.dev fallback." -ForegroundColor Yellow
    }

    Invoke-Download $downloadUrl $zipPath

    if (Test-Path -LiteralPath $extractDir) {
        Remove-Item -LiteralPath $extractDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $extractDir | Out-Null
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force

    $ffmpegExe = Get-ChildItem -LiteralPath $extractDir -Recurse -File -Filter "ffmpeg.exe" | Select-Object -First 1
    $ffprobeExe = Get-ChildItem -LiteralPath $extractDir -Recurse -File -Filter "ffprobe.exe" | Select-Object -First 1

    if (-not $ffmpegExe -or -not $ffprobeExe) {
        throw "FFmpeg archive did not contain ffmpeg.exe and ffprobe.exe."
    }

    if (Test-Path -LiteralPath $ffmpegDir) {
        Remove-Item -LiteralPath $ffmpegDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $ffmpegDir | Out-Null
    Copy-Item -LiteralPath $ffmpegExe.FullName -Destination (Join-Path $ffmpegDir "ffmpeg.exe") -Force
    Copy-Item -LiteralPath $ffprobeExe.FullName -Destination (Join-Path $ffmpegDir "ffprobe.exe") -Force
}

function Test-Install($PythonDir) {
    Write-Step "Verifying install"

    $pythonExe = Join-Path $PythonDir "python.exe"
    $ffmpegExe = Join-Path $BinDir "ffmpeg\ffmpeg.exe"
    $ffprobeExe = Join-Path $BinDir "ffmpeg\ffprobe.exe"

    & $pythonExe -c "import gradio, numpy, PIL; print('Python packages OK')"
    if ($LASTEXITCODE -ne 0) {
        throw "Python package verification failed."
    }

    & $pythonExe -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw "pip dependency check failed."
    }

    & $pythonExe -c "from importlib.metadata import version; from pathlib import Path; req=Path(r'$Requirements'); ok=True; lines=[line.strip() for line in req.read_text().splitlines() if line.strip() and not line.strip().startswith('#')];`nfor line in lines:`n    name, expected = line.split('==', 1); actual = version(name); print(f'{name}=={actual}'); ok = ok and actual == expected`nraise SystemExit(0 if ok else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Installed package versions do not match requirements.txt."
    }

    $ffmpegVersion = & $ffmpegExe -version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "FFmpeg verification failed."
    }
    Write-Host $ffmpegVersion[0]

    $ffprobeVersion = & $ffprobeExe -version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "FFprobe verification failed."
    }
    Write-Host $ffprobeVersion[0]
}

New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
New-Item -ItemType Directory -Path $DownloadDir -Force | Out-Null

$pythonDir = Get-PortablePython
Enable-PythonSite $pythonDir
Install-PipAndRequirements $pythonDir
Install-PortableFfmpeg
Test-Install $pythonDir

Write-Host ""
Write-Host "Portable runtime is ready." -ForegroundColor Green
