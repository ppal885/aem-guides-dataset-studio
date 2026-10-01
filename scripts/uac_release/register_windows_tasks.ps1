<#
Registers the UAC release runner in Windows Task Scheduler (Windows VM).
Run once in an elevated PowerShell:
  .\register_windows_tasks.ps1 -Repo C:\repos\aem-guides-dataset-studio -Config C:\uac-release\config.json -EnvFile C:\uac-release\uac.env
The env file holds JIRA_BASE_URL, JIRA_PAT and COPILOT_GITHUB_TOKEN; restrict it to the task account.
An older "UAC Approved Poster" task is removed: the runner now writes the Acceptance Criteria field itself.
#>
param(
    [Parameter(Mandatory = $true)][string]$Repo,
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$EnvFile,
    [string]$Python = "python"
)

$runner = Join-Path $Repo "scripts\uac_release\uac_release_runner.py"

$runnerAction = New-ScheduledTaskAction -Execute $Python -Argument "`"$runner`" --config `"$Config`" --env-file `"$EnvFile`"" -WorkingDirectory $Repo

$nightly = New-ScheduledTaskTrigger -Daily -At 1:30am
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 10) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "UAC Release Runner" -Action $runnerAction -Trigger $nightly -Settings $settings -Description "Generate UACs with Copilot CLI and write them into the Jira Acceptance Criteria field" -Force
if (Get-ScheduledTask -TaskName "UAC Approved Poster" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName "UAC Approved Poster" -Confirm:$false
}
