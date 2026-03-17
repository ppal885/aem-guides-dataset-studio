# Run evaluation script for AI pipeline
# Usage: .\run_eval.ps1 [-Output report.json] [-Feedback feedback.json] [-NoExecution]
param(
    [string]$Output,
    [string]$Feedback,
    [switch]$NoExecution
)

$backend = Split-Path -Parent $PSScriptRoot
Set-Location $backend

$args = @()
if ($NoExecution) { $args += "--no-execution" }
if ($Output) { $args += "-o", $Output }
if ($Feedback) { $args += "-f", $Feedback }

py -m app.evaluation.run_eval @args
