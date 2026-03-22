param(
    [string]$KeepEmail = "brevintating1@gmail.com",
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

function Resolve-VenvPython {
    param([string]$RequestedPython)

    if ($RequestedPython -and (Test-Path $RequestedPython)) {
        return $RequestedPython
    }

    $candidates = @(
        ".\venv\Scripts\python.exe",
        ".\venv\bin\python"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return $null
}

$pythonExe = Resolve-VenvPython -RequestedPython $Python
if (-not $pythonExe) {
    throw "Virtual environment not found. Run scripts/bootstrap.ps1 first."
}

$script = @'
from rocketcoach.common.persistence import AppDB
import os
import sys

KEEP_EMAIL = os.environ.get("ROCKETCOACH_KEEP_EMAIL", "brevintating1@gmail.com").strip().lower()

try:
    import boto3
except Exception:
    boto3 = None

db = AppDB()
users = db.list_auth_users()
for user in users:
    email = str(user.get("email", "")).strip().lower()
    if not email or email == KEEP_EMAIL:
        continue
    print(f"[prune_accounts] deleting local account: {email}")
    db.delete_account(auth_user_id=int(user["id"]))
    sub = str(user.get("cognito_sub", "") or "").strip()
    if boto3 and sub:
        pool_id = os.environ.get("VITE_COGNITO_USER_POOL_ID") or os.environ.get("COGNITO_USER_POOL_ID")
        if pool_id:
            print(f"[prune_accounts] deleting cognito user: {email}")
            boto3.client("cognito-idp").admin_delete_user(UserPoolId=pool_id, Username=sub)
        else:
            print(f"[prune_accounts] skipped Cognito delete for {email}: missing user pool id", file=sys.stderr)
    elif sub:
        print(f"[prune_accounts] skipped Cognito delete for {email}: boto3 not installed", file=sys.stderr)
'@

$env:ROCKETCOACH_KEEP_EMAIL = $KeepEmail
$script | & $pythonExe -
