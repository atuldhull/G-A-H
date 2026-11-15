#requires -Version 5.1
<#
.SYNOPSIS
Read-only submission/demo preflight. Print commands; never run a model or reset state.
.DESCRIPTION
Checks Git, Python/module availability and immutable v4 identity. Optional TCP
check is unauthenticated loopback only. Never reads credentials, opens databases,
installs packages, starts services, invokes WSL or writes/deletes files.
Exit 0 means these prerequisites passed, not live authorization or comparability.
Exit 1 means incomplete prerequisites/evidence; exit 2 means invalid input.
#>
[CmdletBinding()]
param(
    [string]$Python = 'python',
    [string]$DemoRepo = '',
    [string]$TaskFile = '',
    [string]$Oracle = '',
    [string]$EvidenceRoot = '',
    [string]$DataRoot = '',
    [string]$Bundle = '',
    [switch]$CheckGateway
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
$Config = Join-Path $Repo 'bench/configs/gemini-benchmark-v4.json'
$script:Incomplete = 0

function Write-Check([string]$Status, [string]$Message) {
    Write-Output ('[{0}] {1}' -f $Status, $Message)
    if ($Status -eq 'INCOMPLETE') { $script:Incomplete += 1 }
}

function Quote-Literal([string]$Value) {
    return "'" + $Value.Replace("'", "''") + "'"
}

# Paths/commands are data; never interpret text from a task/config/environment.
foreach ($Value in @($Python, $DemoRepo, $TaskFile, $Oracle, $EvidenceRoot, $DataRoot, $Bundle, $Repo)) {
    if ($Value -match '[\x00-\x1f\x7f-\x9f]') {
        Write-Output '[INCOMPLETE] Control characters in arguments are refused.'
        exit 2
    }
}

Write-Output 'Crocodile submission preflight: read-only, no model calls or database access.'
$Git = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($Git) {
    $Branch = & $Git.Source --no-optional-locks -c core.fsmonitor=false -C $Repo branch --show-current 2>$null
    $BranchExit = $LASTEXITCODE
    $Changes = & $Git.Source --no-optional-locks -c core.fsmonitor=false -C $Repo status --porcelain=v1 --untracked-files=normal --ignore-submodules=all 2>$null
    $StatusExit = $LASTEXITCODE
    if ($BranchExit -eq 0 -and $StatusExit -eq 0 -and $Branch -eq 'person-4' -and -not $Changes) {
        Write-Check 'OK' 'Clean person-4 checkout.'
    } else {
        Write-Check 'INCOMPLETE' 'Require clean person-4; inspect Git status separately. No work was changed.'
    }
} else {
    Write-Check 'INCOMPLETE' 'Git application unavailable.'
}

$Interpreter = Get-Command $Python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($Interpreter) {
    $Python = $Interpreter.Source
    # Isolated stdlib-only inspection: find top-level modules without importing
    # them or repository/exercise code. Do not inspect any credential variables.
    $Probe = @'
import hashlib, importlib.util, json, pathlib, sys
mods = ("pytest", "ruff", "httpx", "typer", "rich", "yaml", "pydantic", "keyring", "crocodile")
config = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
digest = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
print(json.dumps({"version": list(sys.version_info[:3]), "modules": {m: importlib.util.find_spec(m) is not None for m in mods}, "config_id": digest}))
'@
    try {
        # Stdin avoids Windows PowerShell 5.1 native -c quote mangling.
        $Raw = $Probe | & $Python -I -B - $Config 2>$null
        if ($LASTEXITCODE -ne 0) { throw 'probe failed' }
        $Info = ($Raw -join "`n") | ConvertFrom-Json
        if ($Info.version[0] -eq 3 -and $Info.version[1] -eq 12) {
            Write-Check 'OK' ('Python {0}; no project code imported.' -f ($Info.version -join '.'))
        } else {
            Write-Check 'INCOMPLETE' 'Python 3.12 required for this reviewed environment; no substitute installed.'
        }
        foreach ($Module in $Info.modules.PSObject.Properties) {
            if (-not $Module.Value) { Write-Check 'INCOMPLETE' ('Missing installed module: ' + $Module.Name) }
        }
        if ($Info.config_id -eq '026d0a1b238f4675011c268619c051b1ffd3102a264a85e712bf7721f49b1bb4') {
            Write-Check 'OK' 'Immutable gemini-54-v4 fingerprint matches; this is not full runtime validation.'
        } else {
            Write-Check 'INCOMPLETE' 'V4 config fingerprint differs; stop release review.'
        }
    } catch {
        Write-Check 'INCOMPLETE' 'Isolated interpreter/config probe failed; no raw exception or file content printed.'
    }
} else {
    Write-Check 'INCOMPLETE' 'Python application not found; pass the explicit Python 3.12 venv interpreter.'
}

foreach ($InputFile in @(@('DemoRepo', $DemoRepo, 'Container'), @('TaskFile', $TaskFile, 'Leaf'),
                        @('DataRoot', $DataRoot, 'Container'), @('Bundle', $Bundle, 'Container'))) {
    if ($InputFile[1] -and (Test-Path -LiteralPath $InputFile[1] -PathType $InputFile[2])) {
        Write-Check 'OK' ($InputFile[0] + ' exists; contents not executed.')
    } else {
        Write-Check 'INCOMPLETE' ($InputFile[0] + ' not supplied or unavailable; operator must provide a reviewed path.')
    }
}
if (-not $Oracle -or -not $EvidenceRoot) {
    Write-Check 'INCOMPLETE' 'Supply reviewed oracle target and new external evidence directory before recording.'
}
if ($CheckGateway) {
    $Socket = New-Object System.Net.Sockets.TcpClient
    try {
        $Connection = $Socket.ConnectAsync('127.0.0.1', 18080)
        if (-not $Connection.Wait(2000) -or -not $Socket.Connected) { throw 'unreachable' }
        Write-Check 'OK' 'TCP 127.0.0.1:18080 reachable only; no authenticated request or model call sent.'
    } catch {
        Write-Check 'INCOMPLETE' 'TCP 127.0.0.1:18080 unavailable; no credentials or server payload inspected.'
    } finally {
        $Socket.Dispose()
    }
} else {
    Write-Output '[UNVERIFIED] Gateway connectivity not checked; opt in with -CheckGateway for TCP only.'
}
Write-Check 'INCOMPLETE' 'Live version/VK/model/routing/session completeness and authorization require owner evidence.'
Write-Output '[UNVERIFIED] WSL mini installation/settings not inspected; no distro or process started.'

Write-Output "`nCommands to review and run manually (none are executed by prep):"
Write-Output ('$Python = ' + (Quote-Literal $Python))
Write-Output ('$Repo = ' + (Quote-Literal $Repo))
foreach ($Setting in @(@('DemoRepo', $DemoRepo), @('TaskFile', $TaskFile), @('Oracle', $Oracle),
                      @('EvidenceRoot', $EvidenceRoot), @('DataRoot', $DataRoot), @('Bundle', $Bundle))) {
    if ($Setting[1]) {
        Write-Output ('$' + $Setting[0] + ' = ' + (Quote-Literal $Setting[1]))
    } else {
        Write-Output ('# Set $' + $Setting[0] + ' to the reviewed non-secret path/target before using it.')
    }
}
Write-Output @'
Set-Location -LiteralPath $Repo
& $Python -m crocodile run --help
& $Python -m crocodile quote --task-file $TaskFile --repo $DemoRepo --ascii
& $Python -m pytest -v -ra -p no:cacheprovider redteam/tests/test_security_cases.py
& $Python -m pytest -v -p no:cacheprovider tests/gateway/test_budget.py::test_budget_reservation_and_reconcile tests/gateway/test_budget.py::test_budget_exhaustion_raises_denied
& $Python -m ruff check --isolated --target-version py312 --select E4,E7,E9,F --no-cache bench crocodile/ui redteam
$Config = Join-Path $Repo 'bench/configs/gemini-benchmark-v4.json'
& $Python -m bench.canonical --config $Config --data-root $DataRoot --plans "$Bundle/full.json" "$Bundle/shard-1.json" "$Bundle/shard-2.json" "$Bundle/shard-3.json" "$Bundle/shard-4.json"
& $Python -m bench.canonical --config $Config --data-root $DataRoot --require-comparable
# Comparability currently exits 1. No benchmark --execute command is authorized.
# Manual demo recording only after owner authorization and reviewed fixture/output paths:
# & $Python -m crocodile doctor --repo $DemoRepo
# & $Python -m crocodile run --repo $DemoRepo --task-file $TaskFile --test $Oracle --steps 30 --json-out "$EvidenceRoot/agent-receipt.json"
'@
Write-Output ('Preflight incomplete checks: {0}. No files/state/logs changed.' -f $script:Incomplete)
if ($script:Incomplete -gt 0) { exit 1 }
exit 0
