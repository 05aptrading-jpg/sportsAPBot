$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
$log = "D:\Apuestas\mlb_bot\futbol_bot\scheduler.log"
$err = "D:\Apuestas\mlb_bot\futbol_bot\scheduler.err"
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "D:\Apuestas\mlb_bot\futbol_bot\main.py" -WorkingDirectory "D:\Apuestas\mlb_bot\futbol_bot" -RedirectStandardOutput $log -RedirectStandardError $err
Start-Sleep -Seconds 3
Write-Output "Started PID:"
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }
Write-Output "---"
Get-Content $log -Tail 5
