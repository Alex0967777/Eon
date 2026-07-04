[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [string]$DownloadsDirectory,
    [string]$PatchPath,
    [string]$GitPath,
    [switch]$DryRun
)

$ScriptVersion = '1.2.6'

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}


function Resolve-GitExecutable {
    param([string]$RequestedPath)

    $candidates = New-Object System.Collections.Generic.List[string]

    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        $candidates.Add($RequestedPath)
    }

    foreach ($commandName in @('git.exe', 'git')) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($null -ne $command -and -not [string]::IsNullOrWhiteSpace($command.Source)) {
            $candidates.Add($command.Source)
        }
    }

    if ($env:OS -eq 'Windows_NT') {
        $programFiles = [Environment]::GetEnvironmentVariable('ProgramFiles')
        $programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
        $localAppData = [Environment]::GetEnvironmentVariable('LOCALAPPDATA')
        $chocolateyInstall = [Environment]::GetEnvironmentVariable('ChocolateyInstall')

        foreach ($root in @($programFiles, $programFilesX86)) {
            if (-not [string]::IsNullOrWhiteSpace($root)) {
                $candidates.Add((Join-Path $root 'Git\cmd\git.exe'))
                $candidates.Add((Join-Path $root 'Git\bin\git.exe'))
            }
        }

        if (-not [string]::IsNullOrWhiteSpace($localAppData)) {
            $candidates.Add((Join-Path $localAppData 'Programs\Git\cmd\git.exe'))
            $desktopRoot = Join-Path $localAppData 'GitHubDesktop'
            if (Test-Path -LiteralPath $desktopRoot -PathType Container) {
                $desktopVersions = @(
                    Get-ChildItem -LiteralPath $desktopRoot -Directory -Filter 'app-*' -ErrorAction SilentlyContinue |
                        Sort-Object Name -Descending
                )
                foreach ($versionDirectory in $desktopVersions) {
                    $candidates.Add((Join-Path $versionDirectory.FullName 'resources\app\git\cmd\git.exe'))
                    $candidates.Add((Join-Path $versionDirectory.FullName 'resources\app\git\bin\git.exe'))
                }
            }
        }

        if (-not [string]::IsNullOrWhiteSpace($HOME)) {
            $candidates.Add((Join-Path $HOME 'scoop\apps\git\current\cmd\git.exe'))
        }
        if (-not [string]::IsNullOrWhiteSpace($chocolateyInstall)) {
            $candidates.Add((Join-Path $chocolateyInstall 'bin\git.exe'))
        }

        foreach ($registryPath in @(
            'HKLM:\SOFTWARE\GitForWindows',
            'HKLM:\SOFTWARE\WOW6432Node\GitForWindows',
            'HKCU:\SOFTWARE\GitForWindows'
        )) {
            try {
                $installPath = (Get-ItemProperty -LiteralPath $registryPath -ErrorAction Stop).InstallPath
                if (-not [string]::IsNullOrWhiteSpace($installPath)) {
                    $candidates.Add((Join-Path $installPath 'cmd\git.exe'))
                    $candidates.Add((Join-Path $installPath 'bin\git.exe'))
                }
            }
            catch {
                # Registry entry is optional.
            }
        }
    }

    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }

        $expanded = [Environment]::ExpandEnvironmentVariables($candidate)
        if (-not (Test-Path -LiteralPath $expanded -PathType Leaf)) {
            continue
        }

        $resolved = (Resolve-Path -LiteralPath $expanded).Path
        if (-not $seen.Add($resolved)) {
            continue
        }

        $versionOutput = & $resolved --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $versionOutput) {
            return $resolved
        }
    }

    throw 'git.exe was not found. Install Git for Windows or pass -GitPath with the full path to git.exe.'
}

function Resolve-EonRepositoryRoot {
    param([string]$RequestedRoot)

    $candidates = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($RequestedRoot)) {
        $candidates.Add($RequestedRoot)
    }
    $candidates.Add($PSScriptRoot)
    $candidates.Add((Get-Location).Path)
    $candidates.Add('E:\Eon\GitRepo\Eon')

    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate) -or -not (Test-Path -LiteralPath $candidate -PathType Container)) {
            continue
        }

        $resolved = (Resolve-Path -LiteralPath $candidate).Path
        $top = & $script:GitExe -C $resolved rev-parse --show-toplevel 2>$null
        if ($LASTEXITCODE -eq 0 -and $top) {
            # Git for Windows prints paths with forward slashes (E:/repo).
            # Canonicalize the root through System.IO before later prefix checks.
            return [IO.Path]::GetFullPath(([string]$top).Trim())
        }
    }

    throw 'Local Eon Git repository was not found. Pass -RepositoryRoot explicitly.'
}

function Resolve-DownloadsDirectory {
    param([string]$RequestedDirectory)

    if (-not [string]::IsNullOrWhiteSpace($RequestedDirectory)) {
        if (-not (Test-Path -LiteralPath $RequestedDirectory -PathType Container)) {
            throw "Downloads directory was not found: $RequestedDirectory"
        }
        return (Resolve-Path -LiteralPath $RequestedDirectory).Path
    }

    if ($env:OS -eq 'Windows_NT') {
        try {
            $shellFolders = Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders'
            $knownFolder = $shellFolders.'{374DE290-123F-4565-9164-39C4925E467B}'
            if (-not [string]::IsNullOrWhiteSpace($knownFolder)) {
                $expanded = [Environment]::ExpandEnvironmentVariables($knownFolder)
                if (Test-Path -LiteralPath $expanded -PathType Container) {
                    return (Resolve-Path -LiteralPath $expanded).Path
                }
            }
        }
        catch {
            # Fallback below.
        }
    }

    $fallback = Join-Path $HOME 'Downloads'
    if (-not (Test-Path -LiteralPath $fallback -PathType Container)) {
        throw "Downloads directory was not found: $fallback"
    }
    return (Resolve-Path -LiteralPath $fallback).Path
}

function ConvertTo-NativeArgument {
    param([AllowEmptyString()][string]$Value)

    if ($null -eq $Value -or $Value.Length -eq 0) {
        return '""'
    }

    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    # Quote according to the Windows command-line parsing rules used by
    # CommandLineToArgvW. This fallback is required by Windows PowerShell 5.1,
    # whose ProcessStartInfo does not expose ArgumentList.
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $backslashes = 0

    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq [char]92) {
            $backslashes++
            continue
        }

        if ($character -eq [char]34) {
            if ($backslashes -gt 0) {
                [void]$builder.Append(('\' * ($backslashes * 2)))
            }
            [void]$builder.Append('\"')
            $backslashes = 0
            continue
        }

        if ($backslashes -gt 0) {
            [void]$builder.Append(('\' * $backslashes))
            $backslashes = 0
        }
        [void]$builder.Append($character)
    }

    if ($backslashes -gt 0) {
        [void]$builder.Append(('\' * ($backslashes * 2)))
    }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )

    # Do not invoke Git through PowerShell's native-command adapter here.
    # Windows PowerShell 5.1 turns any stderr text into NativeCommandError when
    # ErrorActionPreference is Stop, even when Git exits successfully. Git uses
    # stderr for harmless warnings and normal push progress. Capture both streams
    # through System.Diagnostics.Process and decide success only by ExitCode.
    $allArguments = @('-C', $script:RepoRoot) + @($Arguments)
    $argumentText = (($allArguments | ForEach-Object {
        ConvertTo-NativeArgument ([string]$_)
    }) -join ' ')

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $script:GitExe
    $startInfo.Arguments = $argumentText
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo

    try {
        if (-not $process.Start()) {
            throw 'Failed to start git.exe.'
        }

        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $stdout = $stdoutTask.Result
        $stderr = $stderrTask.Result
        $exitCode = $process.ExitCode
    }
    finally {
        $process.Dispose()
    }

    $script:LastGitExitCode = $exitCode
    $global:LASTEXITCODE = $exitCode

    if ($exitCode -ne 0 -and -not $AllowFailure) {
        $details = @($stdout, $stderr) |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { $_.TrimEnd() }
        $text = ($details -join "`n")
        throw "git $($Arguments -join ' ') exited with code $exitCode.`n$text"
    }

    if ($exitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($stderr)) {
        Write-Host ($stderr.TrimEnd()) -ForegroundColor DarkYellow
    }

    if ([string]::IsNullOrEmpty($stdout)) {
        return @()
    }

    return ,@($stdout -split "`r?`n" | Where-Object { $_ -ne '' })
}

function Get-PatchNumberFromName {
    param([string]$Name)
    if ($Name -notmatch '^Patch_Eon([0-9]+)\.zip$') {
        throw "Invalid patch name: $Name. Expected Patch_EonN.zip"
    }
    return [int]$Matches[1]
}

function Resolve-PatchFile {
    param(
        [string]$RequestedPatch,
        [string]$Downloads
    )

    if (-not [string]::IsNullOrWhiteSpace($RequestedPatch)) {
        if (-not (Test-Path -LiteralPath $RequestedPatch -PathType Leaf)) {
            throw "Patch was not found: $RequestedPatch"
        }
        $resolved = (Resolve-Path -LiteralPath $RequestedPatch).Path
        [void](Get-PatchNumberFromName ([IO.Path]::GetFileName($resolved)))
        return $resolved
    }

    $patches = @(
        Get-ChildItem -LiteralPath $Downloads -File -Filter 'Patch_Eon*.zip' |
            ForEach-Object {
                if ($_.Name -match '^Patch_Eon([0-9]+)\.zip$') {
                    [PSCustomObject]@{ File = $_; Number = [int]$Matches[1] }
                }
            } |
            Sort-Object Number -Descending
    )

    if ($patches.Count -eq 0) {
        throw "No Patch_EonN.zip was found in '$Downloads'"
    }

    return $patches[0].File.FullName
}

function Test-SafeRelativePath {
    param([string]$RelativePath)

    if ([string]::IsNullOrWhiteSpace($RelativePath)) {
        throw 'Patch contains an empty path.'
    }

    $normalized = $RelativePath.Replace('\', '/')
    if ($normalized.StartsWith('/') -or $normalized -match '^[A-Za-z]:') {
        throw "Absolute path is not allowed: $RelativePath"
    }

    $segments = $normalized.Split('/')
    foreach ($segment in $segments) {
        if ($segment -eq '..') {
            throw "Path traversal is not allowed: $RelativePath"
        }
    }

    return $normalized
}

function Get-RepositoryPath {
    param([string]$RelativePath)

    $normalized = Test-SafeRelativePath $RelativePath

    # Always compare canonical full paths. Git for Windows may return E:/repo,
    # while GetFullPath/Join-Path return E:\repo; comparing those raw strings
    # produces a false "escapes repository root" error.
    $canonicalRoot = [IO.Path]::GetFullPath($script:RepoRoot).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $platformRelative = $normalized.Replace('/', [IO.Path]::DirectorySeparatorChar)
    $candidate = [IO.Path]::GetFullPath((Join-Path $canonicalRoot $platformRelative))
    $rootWithSeparator = $canonicalRoot + [IO.Path]::DirectorySeparatorChar

    if (-not $candidate.StartsWith($rootWithSeparator, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escapes repository root: $RelativePath"
    }
    return $candidate
}

function Expand-And-ValidatePatch {
    param(
        [string]$ArchivePath,
        [string]$Destination,
        [string]$ExpectedPatchId
    )

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $archive = [IO.Compression.ZipFile]::OpenRead($ArchivePath)
    try {
        $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        foreach ($entry in $archive.Entries) {
            $name = $entry.FullName.Replace('\', '/')
            if ([string]::IsNullOrWhiteSpace($name)) {
                continue
            }

            [void](Test-SafeRelativePath $name)
            if (-not $seen.Add($name)) {
                throw "Duplicate ZIP entry: $name"
            }

            $allowed = ($name -eq 'patch.json') -or $name.StartsWith('files/') -or $name.StartsWith('ops/') -or $name.StartsWith('notes/')
            if (-not $allowed) {
                throw "Unexpected archive path: $name"
            }

            if ([string]::IsNullOrEmpty($entry.Name)) {
                continue
            }

            $destinationPath = [IO.Path]::GetFullPath((Join-Path $Destination ($name.Replace('/', [IO.Path]::DirectorySeparatorChar))))
            $destinationRoot = [IO.Path]::GetFullPath($Destination).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
            if (-not $destinationPath.StartsWith($destinationRoot, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Unsafe ZIP path: $name"
            }

            $parent = Split-Path -Parent $destinationPath
            if (-not (Test-Path -LiteralPath $parent)) {
                New-Item -ItemType Directory -Path $parent -Force | Out-Null
            }

            $input = $entry.Open()
            try {
                $output = [IO.File]::Open($destinationPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
                try {
                    $input.CopyTo($output)
                }
                finally {
                    $output.Dispose()
                }
            }
            finally {
                $input.Dispose()
            }
        }
    }
    finally {
        $archive.Dispose()
    }

    $metadataPath = Join-Path $Destination 'patch.json'
    if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf)) {
        throw 'patch.json is missing from the patch.'
    }

    $metadata = Get-Content -LiteralPath $metadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($metadata.format -ne 'EonMemoryPatch' -or [int]$metadata.version -ne 1) {
        throw 'Unsupported EonMemoryPatch format.'
    }
    if ($metadata.patchId -ne $ExpectedPatchId) {
        throw "patch.json contains '$($metadata.patchId)', expected '$ExpectedPatchId'"
    }
}

function Read-DeleteOperations {
    param([string]$ExpandedRoot)

    $opsPath = Join-Path $ExpandedRoot 'ops\patch-ops.json'
    if (-not (Test-Path -LiteralPath $opsPath -PathType Leaf)) {
        return @()
    }

    $document = Get-Content -LiteralPath $opsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $document) {
        return @()
    }

    if ($document.PSObject.Properties.Name -contains 'operations') {
        $operations = @($document.operations)
    }
    else {
        $operations = @($document)
    }

    foreach ($operation in $operations) {
        if ($operation.type -ne 'delete_file') {
            throw "Unsupported operation '$($operation.type)'. Only delete_file is allowed."
        }
        [void](Test-SafeRelativePath ([string]$operation.path))
    }

    return $operations
}

function Update-FileHashes {
    Write-Step 'Updating FILE_HASHES.sha256'

    # Do not parse `git ls-files` here. Git for Windows may quote non-ASCII
    # names as C-style octal escapes (for example \320\232...), which are not
    # valid Windows paths. Walk the actual filesystem instead.
    $root = [IO.Path]::GetFullPath($script:RepoRoot)
    $rootPrefix = $root.TrimEnd([char[]]@([char]92, [char]47)) + [IO.Path]::DirectorySeparatorChar

    $directories = New-Object 'System.Collections.Generic.Stack[string]'
    $directories.Push($root)
    $items = New-Object System.Collections.Generic.List[object]

    while ($directories.Count -gt 0) {
        $directory = $directories.Pop()

        foreach ($childDirectory in @(Get-ChildItem -LiteralPath $directory -Directory -Force -ErrorAction Stop)) {
            if ($childDirectory.Name -eq '.git') {
                continue
            }
            $directories.Push($childDirectory.FullName)
        }

        foreach ($file in @(Get-ChildItem -LiteralPath $directory -File -Force -ErrorAction Stop)) {
            $fullPath = [IO.Path]::GetFullPath($file.FullName)
            if (-not $fullPath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw "File escapes repository root while hashing: $fullPath"
            }

            $relative = $fullPath.Substring($rootPrefix.Length).Replace([char]92, [char]47)
            if ($relative -eq 'FILE_HASHES.sha256') { continue }
            if ($relative -eq 'Launch_EON.zip' -or $relative -eq 'backpack.zip') { continue }
            if ($relative -match '(^|/)Patch_Eon[0-9]+\.zip$') { continue }

            $items.Add([PSCustomObject]@{
                Relative = $relative
                FullPath = $fullPath
            })
        }
    }

    $array = $items.ToArray()
    [Array]::Sort($array, [System.Collections.Generic.Comparer[object]]::Create({
        param($left, $right)
        return [StringComparer]::Ordinal.Compare([string]$left.Relative, [string]$right.Relative)
    }))

    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($item in $array) {
        $hash = (Get-FileHash -LiteralPath $item.FullPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $lines.Add("$hash  $($item.Relative)")
    }

    $content = ($lines -join "`n") + "`n"
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText((Join-Path $script:RepoRoot 'FILE_HASHES.sha256'), $content, $encoding)
}

function Test-RepositoryReady {
    $inside = (Invoke-Git -Arguments @('rev-parse', '--is-inside-work-tree')) -join ''
    if ($inside.Trim() -ne 'true') {
        throw 'The specified directory is not a Git working tree.'
    }

    $status = Invoke-Git -Arguments @('status', '--porcelain', '--untracked-files=all')
    if (@($status | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }).Count -ne 0) {
        throw "Eon working tree is not clean. Commit or stash existing changes first.`n$($status -join "`n")"
    }

    $branch = ((Invoke-Git -Arguments @('branch', '--show-current')) -join '').Trim()
    if ([string]::IsNullOrWhiteSpace($branch)) {
        throw 'Detached HEAD is not supported.'
    }

    $upstreamResult = Invoke-Git -Arguments @('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}') -AllowFailure
    if ($script:LastGitExitCode -ne 0 -or @($upstreamResult).Count -eq 0) {
        throw "No upstream is configured for branch '$branch'."
    }

    Invoke-Git -Arguments @('fetch', '--quiet') | Out-Null
    $upstream = (($upstreamResult) -join '').Trim()
    $countsText = ((Invoke-Git -Arguments @('rev-list', '--left-right', '--count', "HEAD...$upstream")) -join ' ').Trim()
    $parts = $countsText -split '\s+'
    if ($parts.Count -lt 2) {
        throw "Could not determine divergence from upstream: $countsText"
    }

    return [PSCustomObject]@{
        Branch = $branch
        Upstream = $upstream
        Ahead = [int]$parts[0]
        Behind = [int]$parts[1]
    }
}

Write-Host "Apply-EonMemory version: $ScriptVersion"
$script:GitExe = Resolve-GitExecutable $GitPath
Write-Host "Git:            $script:GitExe"
$script:RepoRoot = Resolve-EonRepositoryRoot $RepositoryRoot
$downloads = Resolve-DownloadsDirectory $DownloadsDirectory
$resolvedPatch = Resolve-PatchFile -RequestedPatch $PatchPath -Downloads $downloads
$patchName = [IO.Path]::GetFileName($resolvedPatch)
$patchNumber = Get-PatchNumberFromName $patchName
$patchId = "Patch_Eon$patchNumber"
$commitMessage = "Apply $patchId"

Write-Host "Eon repository: $script:RepoRoot"
Write-Host "Patch:          $resolvedPatch"

$sync = Test-RepositoryReady

# Recovery path: a prior run may have committed successfully but failed during push.
if ($sync.Ahead -eq 1 -and $sync.Behind -eq 0) {
    $headSubject = ((Invoke-Git -Arguments @('log', '-1', '--pretty=%s')) -join '').Trim()
    if ($headSubject -eq $commitMessage) {
        if ($DryRun) {
            Write-Host "DryRun: local commit '$commitMessage' already exists and is waiting for push." -ForegroundColor Yellow
            exit 0
        }
        Write-Step "Retrying push for existing commit '$commitMessage'"
        Invoke-Git -Arguments @('push') | Out-Null
        Remove-Item -LiteralPath $resolvedPatch -Force
        Write-Host "$patchId was pushed successfully; patch archive was removed from Downloads." -ForegroundColor Green
        exit 0
    }
}

if ($sync.Ahead -ne 0 -or $sync.Behind -ne 0) {
    throw "Local branch diverges from $($sync.Upstream): ahead=$($sync.Ahead), behind=$($sync.Behind). Synchronize the repository manually."
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("EonMemoryPatch_" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$changesStarted = $false
$commitCreated = $false

try {
    Write-Step 'Validating and extracting patch'
    Expand-And-ValidatePatch -ArchivePath $resolvedPatch -Destination $tempRoot -ExpectedPatchId $patchId
    $operations = @(Read-DeleteOperations $tempRoot)

    $filesRoot = Join-Path $tempRoot 'files'
    $replacementFiles = @()
    if (Test-Path -LiteralPath $filesRoot -PathType Container) {
        $replacementFiles = @(
            Get-ChildItem -LiteralPath $filesRoot -File -Recurse |
                Sort-Object FullName
        )
    }

    Write-Host "Full files to write: $($replacementFiles.Count)"
    Write-Host "Files to delete:     $($operations.Count)"
    foreach ($file in $replacementFiles) {
        $relative = $file.FullName.Substring($filesRoot.Length).TrimStart([char]92, [char]47)
        Write-Host "  WRITE  $($relative.Replace('\', '/'))"
    }
    foreach ($operation in $operations) {
        Write-Host "  DELETE $($operation.path)"
    }

    if ($DryRun) {
        Write-Host 'DryRun PASS: patch is valid; repository was not changed.' -ForegroundColor Green
        exit 0
    }

    $changesStarted = $true
    Write-Step 'Writing full files'
    foreach ($file in $replacementFiles) {
        $relative = $file.FullName.Substring($filesRoot.Length).TrimStart([char]92, [char]47)
        $destination = Get-RepositoryPath $relative
        $parent = Split-Path -Parent $destination
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
    }

    Write-Step 'Deleting declared files'
    foreach ($operation in $operations) {
        $destination = Get-RepositoryPath ([string]$operation.path)
        $missingOk = $false
        if ($operation.PSObject.Properties.Name -contains 'missing_ok') {
            $missingOk = [bool]$operation.missing_ok
        }

        if (Test-Path -LiteralPath $destination -PathType Leaf) {
            Remove-Item -LiteralPath $destination -Force
        }
        elseif (-not $missingOk) {
            throw "File declared for deletion does not exist: $($operation.path)"
        }
    }

    Update-FileHashes

    Write-Step 'Checking Git diff'
    Invoke-Git -Arguments @('diff', '--check') | Out-Null
    $statusAfter = Invoke-Git -Arguments @('status', '--porcelain', '--untracked-files=all')
    if (@($statusAfter | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }).Count -eq 0) {
        throw 'Patch produced no changes.'
    }

    Write-Step "Commit '$commitMessage'"
    Invoke-Git -Arguments @('add', '-A') | Out-Null
    Invoke-Git -Arguments @('commit', '-m', $commitMessage) | Out-Null
    $commitCreated = $true

    Write-Step 'Pushing to GitHub'
    try {
        Invoke-Git -Arguments @('push') | Out-Null
    }
    catch {
        Write-Host 'Commit was created locally, but push failed. The archive remains in Downloads; run the BAT again after fixing the cause.' -ForegroundColor Yellow
        throw
    }

    Remove-Item -LiteralPath $resolvedPatch -Force
    $commitSha = ((Invoke-Git -Arguments @('rev-parse', 'HEAD')) -join '').Trim()
    Write-Host "$patchId was applied successfully; commit $commitSha was pushed to GitHub." -ForegroundColor Green
    Write-Host 'Patch archive was removed from Downloads.' -ForegroundColor Green
}
catch {
    if ($changesStarted -and -not $commitCreated) {
        Write-Host 'Failure before commit: resetting working tree to HEAD.' -ForegroundColor Yellow
        Invoke-Git -Arguments @('reset', '--hard', 'HEAD') -AllowFailure | Out-Null
        Invoke-Git -Arguments @('clean', '-fd') -AllowFailure | Out-Null
    }
    throw
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
