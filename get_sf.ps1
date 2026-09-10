$dst = "C:\Users\theop\Documents\chessathon\tools\stockfish"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
try {
  $r = Invoke-RestMethod "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest" -Headers @{ "User-Agent"="calib" }
  $asset = $r.assets | Where-Object { $_.name -like "*windows-x86-64-avx2*" -and $_.name -like "*.zip" } | Select-Object -First 1
  if (-not $asset) { $asset = $r.assets | Where-Object { $_.name -like "*windows-x86-64*" -and $_.name -like "*.zip" } | Select-Object -First 1 }
  "asset: " + $asset.name | Out-File "$dst\dl.log"
  Invoke-WebRequest $asset.browser_download_url -OutFile "$dst\sf.zip"
  "downloaded " + (Get-Item "$dst\sf.zip").Length + " bytes" | Out-File "$dst\dl.log" -Append
  Expand-Archive "$dst\sf.zip" -DestinationPath $dst -Force
  $exe = Get-ChildItem -Recurse $dst -Filter *.exe | Select-Object -First 1
  $exe.FullName | Out-File "$dst\sf_path.txt" -Encoding ASCII
  "exe: " + $exe.FullName | Out-File "$dst\dl.log" -Append
  & $exe.FullName bench 2>&1 | Select-String "Nodes/second" | Out-File "$dst\dl.log" -Append
  "OK" | Out-File "$dst\dl.log" -Append
} catch { "FAILED: " + $_.Exception.Message | Out-File "$dst\dl.log" -Append }
