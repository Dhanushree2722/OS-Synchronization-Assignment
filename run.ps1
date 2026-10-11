# Runs all four programs one after another. Each one writes its own simulation.html.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python readers_writers\semaphore\readers_writers.py
python readers_writers\monitor\readers_writers_monitor.py
python dining_philosophers\semaphore\dining_philosophers_semaphore.py
python dining_philosophers\monitor\dining_philosophers_monitor.py
Copy-Item readers_writers\semaphore\simulation.html generated_html\readers_writers_semaphore.html -Force
Copy-Item readers_writers\monitor\simulation.html generated_html\readers_writers_monitor.html -Force
Copy-Item dining_philosophers\semaphore\simulation.html generated_html\dining_philosophers_semaphore.html -Force
Copy-Item dining_philosophers\monitor\simulation.html generated_html\dining_philosophers_monitor.html -Force
