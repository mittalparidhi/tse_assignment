$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$logDirectory = Join-Path $projectRoot "audit\test_logs"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDirectory "test_run_$stamp.txt"
$tempFile = Join-Path $logDirectory "capture_$stamp.tmp"
$indexPath = Join-Path $logDirectory "test_log_index.csv"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
@(
    "Project: $projectRoot"
    "Timestamp: $timestamp"
    "Python: $(python --version 2>&1)"
    "Test framework: pytest"
) | Set-Content -Path $logFile -Encoding utf8

function Invoke-LoggedPython {
    param(
        [string]$Label,
        [string[]]$PythonArgs
    )

    Add-Content -Path $logFile -Value "`r`n=== $Label ==="
    Write-Host "`n=== $Label ===" -ForegroundColor Cyan

    & python @PythonArgs *> $tempFile
    $exitCode = $LASTEXITCODE

    if (Test-Path $tempFile) {
        foreach ($line in Get-Content -LiteralPath $tempFile) {
            Add-Content -LiteralPath $logFile -Value $line
            Write-Host $line
        }
        Remove-Item $tempFile -Force
    }

    Add-Content -Path $logFile -Value "$Label`_EXIT_CODE=$exitCode"
    return [int]$exitCode
}

$pytestExitCode = Invoke-LoggedPython `
    -Label "PYTEST_FULL_SUITE" `
    -PythonArgs @("-m", "pytest", "-q")

$examplesExitCode = -1
$buildExitCode = -1

if ($pytestExitCode -eq 0) {
    $examplesExitCode = Invoke-LoggedPython `
        -Label "RETRIEVAL_EXAMPLES" `
        -PythonArgs @("-m", "scripts.run_retrieval_examples")
}

if ($pytestExitCode -eq 0 -and $examplesExitCode -eq 0) {
    $buildExitCode = Invoke-LoggedPython `
        -Label "RUNTIME_BUILD" `
        -PythonArgs @(".\scripts\build_runtime_state.py")
}

$finalStatus = "PASS"
if ($pytestExitCode -ne 0 -or
    $examplesExitCode -ne 0 -or
    $buildExitCode -ne 0) {
    $finalStatus = "FAIL"
}

Add-Content -Path $logFile -Value "`r`nFINAL_STATUS=$finalStatus"

# Append the run to the index while preserving all existing rows and columns.
$existingRows = @()
$existingColumns = @()

if (Test-Path $indexPath) {
    $existingRows = @(Import-Csv -LiteralPath $indexPath)
    if ($existingRows.Count -gt 0) {
        $existingColumns = @(
            $existingRows[0].PSObject.Properties.Name
        )
    }
}

$entry = [ordered]@{
    Timestamp = $timestamp
    TestFramework = "pytest"
    PytestExitCode = $pytestExitCode
    RetrievalExamplesExitCode = $examplesExitCode
    RuntimeBuildExitCode = $buildExitCode
    FinalStatus = $finalStatus
    LogFile = $logFile
}

$columns = @(
    @($existingColumns) + @($entry.Keys) |
    Select-Object -Unique
)

$rowsToWrite = @(
    foreach ($oldRow in $existingRows) {
        $record = [ordered]@{}
        foreach ($column in $columns) {
            if ($oldRow.PSObject.Properties.Name -contains $column) {
                $record[$column] = $oldRow.$column
            } else {
                $record[$column] = ""
            }
        }
        [pscustomobject]$record
    }

    $newRecord = [ordered]@{}
    foreach ($column in $columns) {
        if ($entry.Contains($column)) {
            $newRecord[$column] = $entry[$column]
        } else {
            $newRecord[$column] = ""
        }
    }
    [pscustomobject]$newRecord
)

$indexTemp = "$indexPath.tmp"
$rowsToWrite |
    Export-Csv -LiteralPath $indexTemp -NoTypeInformation -Encoding UTF8
Move-Item -LiteralPath $indexTemp -Destination $indexPath -Force

Write-Host "`nFinal status: $finalStatus"
Write-Host "Log saved: $logFile"
Write-Host "Index updated: $indexPath"

if ($pytestExitCode -ne 0) {
    exit $pytestExitCode
}
if ($examplesExitCode -ne 0) {
    exit $examplesExitCode
}
if ($buildExitCode -ne 0) {
    exit $buildExitCode
}
