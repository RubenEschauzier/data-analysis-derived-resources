#!/usr/bin/env bash
# Where the engine's CPU goes on q16 over time: pattern-only vs derived full (FILTER pushdown), 3 rounds, alternating.
# Profiles in prof/PW-<config>-r<n>/, analysis: python3 analyse_windows.py (CPU s per 5 s window since the query).
cd "$(dirname "$0")"
export ENGINE_MOUNTS=$(bash mounts.sh)
D=jbr-experiment-fedshop-discovery-full-experiment-combination_0-sparql-endpoint-comunica:latest
PO=jbr-experiment-fedshop-discovery-full-experiment-combination_1-sparql-endpoint-comunica:latest
for r in 1 2 3; do
  ENGINE_ENV= python3 profile_windows.py PW-pattern-r$r $PO 'q16#0'
  ENGINE_ENV=DERIVED_FILTER_PUSHDOWN=1 python3 profile_windows.py PW-derived-r$r $D 'q16#0'
done
echo DONE
