$ErrorActionPreference = "Stop"

$apiUrl = "https://api.github.com/repos/whoisjayd/notewise/releases/latest"
$installDir = if ($env:NOTEWISE_INSTALL_DIR) {
    $env:NOTEWISE_INSTALL_DIR
}
else {
    Join-Path $env:LOCALAPPDATA "Programs\\NoteWise"
}

$architecture = switch ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture) {
    "X64" { "x64" }
    "Arm64" { "arm64" }
    default { throw "Unsupported CPU architecture." }
}

$release = Invoke-RestMethod -Uri $apiUrl -Headers @{
    Accept = "application/vnd.github+json"
    "User-Agent" = "NoteWise-Installer"
}

$asset = $release.assets | Where-Object {
    $_.name -match "notewise-v.+-windows-$architecture\.zip$"
} | Select-Object -First 1
$checksumAsset = $release.assets | Where-Object {
    $_.name -eq "SHA256SUMS.txt"
} | Select-Object -First 1

if (-not $asset -or -not $checksumAsset) {
    throw "Could not resolve the Windows release assets for this architecture."
}

$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("notewise-install-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tempDir | Out-Null

try {
    $archivePath = Join-Path $tempDir $asset.name
    $checksumPath = Join-Path $tempDir $checksumAsset.name

    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $archivePath
    Invoke-WebRequest -Uri $checksumAsset.browser_download_url -OutFile $checksumPath

    $expectedChecksum = Get-Content $checksumPath |
        Where-Object { $_ -match [regex]::Escape($asset.name) } |
        ForEach-Object { ($_ -split "\s+")[0] } |
        Select-Object -First 1

    $actualChecksum = (Get-FileHash -Algorithm SHA256 -Path $archivePath).Hash.ToLowerInvariant()
    if (-not $expectedChecksum -or $expectedChecksum.ToLowerInvariant() -ne $actualChecksum) {
        throw "Checksum verification failed for $($asset.name)."
    }

    $extractDir = Join-Path $tempDir "extracted"
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractDir -Force

    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    Copy-Item (Join-Path $extractDir "notewise.exe") (Join-Path $installDir "notewise.exe") -Force

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pathEntries = @()
    if ($userPath) {
        $pathEntries = $userPath.Split(";") | Where-Object { $_ }
    }
    if ($pathEntries -notcontains $installDir) {
        $updatedPath = if ($userPath) { "$userPath;$installDir" } else { $installDir }
        [Environment]::SetEnvironmentVariable("Path", $updatedPath, "User")
        $env:Path = "$env:Path;$installDir"
    }

    Write-Host "Installed NoteWise to $installDir"
    Write-Host "Run: notewise version"
    Write-Host "Open a new terminal if `notewise` is not immediately available."
}
finally {
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
