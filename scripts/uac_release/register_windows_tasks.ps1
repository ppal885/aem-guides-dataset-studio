<#
Registers the two UAC release tasks in Windows Task Scheduler (Windows VM).
Run once in an elevated PowerShell:
  .\register_windows_tasks.ps1 -Repo C:\repos\aem-guides-dataset-studio -Config C:\uac-release\config.json -EnvFile C:\uac-release\uac.env
The env file holds JIRA_BASE_URL, JIRA_PAT and COPILOT_GITHUB_TOKEN; restrict it to the task account.
#>
param(
    [Parameter(Mandatory = $true)][string]$Repo,
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$EnvFile,
    [string]$Python = "python"
)

$runner = Join-Path $Repo "scripts\uac_release\uac_release_runner.py"
$poster = Join-Path $Repo "scripts\uac_release\uac_approved_poster.py"

$runnerAction = New-ScheduledTaskAction -Execute $Python -Argument "`"$runner`" --config `"$Config`" --env-file `"$EnvFile`"" -WorkingDirectory $Repo
$posterAction = New-ScheduledTaskAction -Execute $Python -Argument "`"$poster`" --config `"$Config`" --env-file `"$EnvFile`"" -WorkingDirectory $Repo

$nightly = New-ScheduledTaskTrigger -Daily -At 1:30am
$every30 = New-ScheduledTaskTrigger -Once -At 8:00am -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Hours 12)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 10) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "UAC Release Runner" -Action $runnerAction -Trigger $nightly -Settings $settings -Description "Generate draft UACs with Copilot CLI and post them for QE review" -Force
Register-ScheduledTask -TaskName "UAC Approved Poster" -Action $posterAction -Trigger $every30 -Settings $settings -Description "Copy QE-approved draft UACs into the Jira Acceptance Criteria field" -Force
