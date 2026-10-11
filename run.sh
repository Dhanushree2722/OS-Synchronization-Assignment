#!/bin/sh
# Runs all four programs one after another. Each one writes its own simulation.html.
set -e
cd "$(dirname "$0")"
python3 readers_writers/semaphore/readers_writers.py
python3 readers_writers/monitor/readers_writers_monitor.py
python3 dining_philosophers/semaphore/dining_philosophers_semaphore.py
python3 dining_philosophers/monitor/dining_philosophers_monitor.py
mkdir -p generated_html
cp readers_writers/semaphore/simulation.html generated_html/readers_writers_semaphore.html
cp readers_writers/monitor/simulation.html generated_html/readers_writers_monitor.html
cp dining_philosophers/semaphore/simulation.html generated_html/dining_philosophers_semaphore.html
cp dining_philosophers/monitor/simulation.html generated_html/dining_philosophers_monitor.html
