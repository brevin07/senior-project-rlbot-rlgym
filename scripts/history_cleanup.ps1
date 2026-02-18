param(
    [string]$Branch = "cleanup/history-rewrite"
)

$ErrorActionPreference = "Stop"

Write-Host "This script rewrites git history. Coordinate with collaborators before running."
Write-Host "Creating branch: $Branch"
git checkout -b $Branch

if (-not (Get-Command git-filter-repo -ErrorAction SilentlyContinue)) {
    throw "git-filter-repo is required. Install it first."
}

$paths = @(
    "rlbot_training/rlviser",
    "rlbot_training/rlviser.exe",
    "rlbot_training/rlviser-0.8.1.zip",
    "rlbot_training/rattletrap",
    "rlbot_training/data/checkpoints",
    "rlbot_training/wandb",
    "Milestone_1/physics_data.json",
    "Milestone_1/raw_physics.csv",
    "Milestone_1/player_physics.csv",
    "Milestone_1/player_physics_v3.csv"
)

$args = @("--force")
foreach ($p in $paths) {
    $args += @("--path", $p)
}
$args += "--invert-paths"

Write-Host "Running git filter-repo..."
git filter-repo @args

Write-Host "History rewrite completed locally."
Write-Host "Validate with: git count-objects -vH"
Write-Host "Then push with force-with-lease when ready."
