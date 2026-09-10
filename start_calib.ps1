# Idempotent launcher: refuses to start a second calibration run.
# Necessary because the remote shell retries on timeout, which was silently
# launching duplicate matches and putting 12 engine processes on 6 cores.
$d = "C:\Users\theop\Documents\chessathon"
$existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*calibrate.py*' }
if ($existing) {
    "ALREADY RUNNING (pid " + ($existing.ProcessId -join ',') + ") - not starting another"
    exit 0
}
$lock = "$d\.calib.lock"
if (Test-Path $lock) {
    $age = (Get-Date) - (Get-Item $lock).LastWriteTime
    if ($age.TotalSeconds -lt 30) { "lock is fresh - not starting another"; exit 0 }
}
New-Item -ItemType File -Path $lock -Force | Out-Null
Remove-Item "$d\calib_*.log","$d\calibrate.log","$d\calibrate.err" -ErrorAction SilentlyContinue
Start-Process -FilePath "$d\.venv\Scripts\python.exe" `
    -ArgumentList 'tests\calibrate.py','--start','2400','--step','300','--pairs','8','--base','10000','--inc','100','--workers','3' `
    -WorkingDirectory $d `
    -RedirectStandardOutput "$d\calibrate.log" -RedirectStandardError "$d\calibrate.err" `
    -WindowStyle Hidden
"launched at " + (Get-Date -Format 'HH:mm:ss')
