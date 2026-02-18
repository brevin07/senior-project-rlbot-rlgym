param(
    [string]$DefaultScenario = "",
    [string]$ScenarioRoot = "",
    [double]$BotSkill = 1.0,
    [ValidateSet("tuck", "none")] [string]$NoBotMode = "tuck",
    [ValidateSet("epic", "steam", "auto")] [string]$Launcher = "epic",
    [switch]$AttachOnly,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$argsList = @()
if ($DefaultScenario) {
    $argsList += @("-DefaultScenario", $DefaultScenario)
}
if ($ScenarioRoot) {
    $argsList += @("-ScenarioRoot", $ScenarioRoot)
}
if ($NoBotMode) {
    $argsList += @("-NoBotMode", $NoBotMode)
}
if ($Launcher) {
    $argsList += @("-Launcher", $Launcher)
}
$argsList += @("-BotSkill", "$BotSkill")
if ($AttachOnly) {
    $argsList += "-AttachOnly"
}
if ($NoBrowser) {
    $argsList += "-NoBrowser"
}

& powershell -ExecutionPolicy Bypass -File ".\scripts\launch_live_analysis.ps1" @argsList
