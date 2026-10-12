<#
.SYNOPSIS
    Re-runs only the attachment step (+ everything downstream: XML, Muscle Wrapping 2.0,
    statistics) of an existing pipeline run with a different attachment method.
    Segmentation, meshing and STAPLE are reused from the base run, so CPD vs RNRR
    are compared on exactly the same bones and muscle meshes.

.EXAMPLE
    # from repo root (C:\msk-PIPE), after a finished atlas_based (CPD) run_1:
    .\tools\run_rnrr_on_existing_run.ps1 -BaseRun run_1 -NewRun run_2 -DryRun
    .\tools\run_rnrr_on_existing_run.ps1 -BaseRun run_1 -NewRun run_2
    .\tools\run_rnrr_on_existing_run.ps1 -BaseRun run_1 -NewRun run_2 -SkipDryRun
#>
param(
    [string]$BaseRun = "run_1",
    [string]$NewRun  = "run_2",
    [ValidateSet("fast_rnrr", "atlas_based", "proximity_based")]
    [string]$Method  = "fast_rnrr",
    [string]$Cores   = "all",
    [switch]$DryRun,
    [switch]$SkipDryRun
)

$ErrorActionPreference = "Stop"
$Root      = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $Root
$OutBase   = Join-Path $Root "data\output"
$Src       = Join-Path $OutBase $BaseRun
$Dst       = Join-Path $OutBase $NewRun
$Mamba     = Join-Path $Root "bin\micromamba.exe"
$EnvBase   = Join-Path $Root "envs\msk_base"
$PyBase    = Join-Path $EnvBase "python.exe"
$LogDir    = Join-Path $Dst "logs"

if (-not (Test-Path (Join-Path $Src "bone_model.osim"))) { throw "Base run $Src has no bone_model.osim - run the full pipeline first." }
if (-not (Test-Path $Mamba))  { throw "micromamba not found at $Mamba - run 'python -m runner' once first." }

# micromamba.exe crashes on Windows with 0xC0000409 (STATUS_STACK_BUFFER_OVERRUN) when
# MAMBA_ROOT_PREFIX is not set. runner/micromamba.py sets exactly these variables
# (make_mamba_env), so do the same here for a standalone invocation.
$EnvsDir = Join-Path $Root "envs"
if (-not $env:MAMBA_ROOT_PREFIX) { $env:MAMBA_ROOT_PREFIX = $EnvsDir }
if (-not $env:MAMBA_PKGS_DIRS -and -not $env:CONDA_PKGS_DIRS) { $env:MAMBA_PKGS_DIRS = Join-Path $env:MAMBA_ROOT_PREFIX "pkgs" }
$PipCache = Join-Path $env:MAMBA_ROOT_PREFIX "pip_cache"
New-Item -ItemType Directory -Force -Path $PipCache | Out-Null
if (-not $env:PIP_CACHE_DIR) { $env:PIP_CACHE_DIR = $PipCache }
$env:CONDA_EXE = $Mamba

# 1) Copy the base run WITHOUT attachment-dependent outputs (robocopy keeps timestamps)
if (-not (Test-Path $Dst)) {
    Write-Host "Copying $BaseRun -> $NewRun (without attachments/Experiments/statistics)..." -ForegroundColor Cyan
    robocopy $Src $Dst /E /COPY:DAT /DCOPY:DAT /NFL /NDL /NJH /NJS /NP `
        /XD attachments Experiments statistics logs .snakemake `
        /XF pipeline_model.osim setup_MuscleGeneratorTool.xml "extract_attachments_*.txt" `
            prepare_muscle_wrapping.txt run_muscle_wrapping.txt statistics_compare.txt | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }
} else {
    Write-Host "$NewRun already exists - reusing it." -ForegroundColor Yellow
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# 2) Config override: same config.json, only attachment_extraction.method changed
$Override = Join-Path $Dst "config_override_$Method.json"
& $PyBase -c "import json,sys; c=json.load(open('config/config.json',encoding='utf-8')); c['attachment_extraction']['method']=sys.argv[1]; json.dump(c,open(sys.argv[2],'w',encoding='utf-8'),indent=2)" $Method $Override
if ($LASTEXITCODE -ne 0) { throw "Could not write config override." }

# Fast-RNRR binaries: same check/download as the runner pre-flight
if ($Method -eq "fast_rnrr") {
    & $PyBase -c "import json,sys; from runner.external_tools import ensure_fast_rnrr; p=json.load(open('config/config.json',encoding='utf-8')).get('paths',{}); sys.exit(0 if ensure_fast_rnrr(p,'fast_rnrr') else 1)"
    if ($LASTEXITCODE -ne 0) { throw "Fast-RNRR binaries are not available." }
}

# 3) Snakemake (same invocation as runner/pipeline.py) restricted to mtime triggers,
#    so copied upstream files are NOT recomputed.
$SmkArgs = @(
    "run", "-p", $EnvBase, "snakemake",
    "--snakefile", "workflow/Snakefile",
    "--cores", $Cores,
    "--resources", "segmentation_mutex=1",
    "--latency-wait", "30",
    "--configfile", $Override,
    "--config", "run_id=$NewRun",
    "--rerun-triggers", "mtime",
    "--rerun-incomplete"
)

if (-not $SkipDryRun) {
    Write-Host "`nDry-run (check that ONLY extract_attachments_*, prepare_muscle_wrapping, run_muscle_wrapping, statistics rules are listed):" -ForegroundColor Cyan
    $outLog = Join-Path $LogDir "snakemake_dryrun.out.log"
    $errLog = Join-Path $LogDir "snakemake_dryrun.err.log"
    $argLine = (($SmkArgs + @("-n", "--quiet", "rules")) | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
    $proc = Start-Process -FilePath $Mamba -ArgumentList $argLine -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog
    Get-Content $outLog, $errLog -ErrorAction SilentlyContinue | Write-Host
    if ($proc.ExitCode -ne 0) {
        throw "Snakemake dry-run failed (exit $($proc.ExitCode)). Full output is printed above and saved in $LogDir"
    }
    if ($DryRun) { return }
}

Write-Host "`nRunning $Method on $NewRun ..." -ForegroundColor Cyan
& $Mamba @SmkArgs
if ($LASTEXITCODE -ne 0) { throw "Snakemake failed (exit $LASTEXITCODE) - see the output above." }

Write-Host "`nDone. Compare with:" -ForegroundColor Green
Write-Host "  envs\msk_base\python.exe src\python\compare_attachment_methods.py --run CPD=data\output\$BaseRun --run RNRR=data\output\$NewRun --output data\output\compare_${BaseRun}_vs_${NewRun}"
