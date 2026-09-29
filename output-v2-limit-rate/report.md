# Derived-resource benchmark analysis

Engines compared: `default`, `derived-resources`. 900 runs over 15 templates x 5 instances x 6 replications.

## Result agreement per template

| template               |   instances | runs_ok default   | runs_ok derived-resources   |   results_mismatch |   hash_mismatch |   nondeterministic |   no_data | status   |
|:-----------------------|------------:|:------------------|:----------------------------|-------------------:|----------------:|-------------------:|----------:|:---------|
| interactive-discover-1 |           5 | 30/30             | 30/30                       |                  0 |               0 |                  0 |         0 | match    |
| interactive-discover-2 |           5 | 30/30             | 0/30                        |                  0 |               0 |                  0 |         5 | no data  |
| interactive-discover-3 |           5 | 29/30             | 0/30                        |                  0 |               0 |                  0 |         5 | no data  |
| interactive-discover-4 |           5 | 30/30             | 0/30                        |                  0 |               0 |                  0 |         5 | no data  |
| interactive-discover-5 |           5 | 30/30             | 30/30                       |                  0 |               0 |                  0 |         0 | match    |
| interactive-discover-6 |           5 | 22/30             | 30/30                       |                  0 |               0 |                  0 |         1 | no data  |
| interactive-discover-7 |           5 | 18/30             | 18/30                       |                  0 |               0 |                  0 |         2 | no data  |
| interactive-discover-8 |           5 | 30/30             | 0/30                        |                  0 |               0 |                  4 |         5 | no data  |
| interactive-short-1    |           5 | 30/30             | 0/30                        |                  0 |               0 |                  0 |         5 | no data  |
| interactive-short-2    |           5 | 0/30              | 0/30                        |                  0 |               0 |                  0 |         5 | no data  |
| interactive-short-3    |           5 | 0/30              | 0/30                        |                  0 |               0 |                  0 |         5 | no data  |
| interactive-short-4    |           5 | 30/30             | 30/30                       |                  0 |               0 |                  0 |         0 | match    |
| interactive-short-5    |           5 | 30/30             | 30/30                       |                  0 |               0 |                  0 |         0 | match    |
| interactive-short-6    |           5 | 0/30              | 0/30                        |                  0 |               0 |                  0 |         5 | no data  |
| interactive-short-7    |           5 | 0/30              | 0/30                        |                  0 |               0 |                  0 |         5 | no data  |

## Query instances that disagree (0)

_None._

## Completion

How every run ended. Timing tables that drop failed runs are biased by whatever is in this table, so read it first.

| template               | completed default   |   timeout default |   crash default |   unsupported default | completed derived-resources   |   timeout derived-resources |   crash derived-resources |   unsupported derived-resources |
|:-----------------------|:--------------------|------------------:|----------------:|----------------------:|:------------------------------|----------------------------:|--------------------------:|--------------------------------:|
| interactive-discover-1 | 30/30               |                 0 |               0 |                     0 | 30/30                         |                           0 |                         0 |                               0 |
| interactive-discover-2 | 30/30               |                 0 |               0 |                     0 | 0/30                          |                           0 |                        30 |                               0 |
| interactive-discover-3 | 29/30               |                 1 |               0 |                     0 | 0/30                          |                           0 |                        30 |                               0 |
| interactive-discover-4 | 30/30               |                 0 |               0 |                     0 | 0/30                          |                           0 |                        30 |                               0 |
| interactive-discover-5 | 30/30               |                 0 |               0 |                     0 | 30/30                         |                           0 |                         0 |                               0 |
| interactive-discover-6 | 22/30               |                 8 |               0 |                     0 | 30/30                         |                           0 |                         0 |                               0 |
| interactive-discover-7 | 18/30               |                12 |               0 |                     0 | 18/30                         |                          12 |                         0 |                               0 |
| interactive-discover-8 | 30/30               |                 0 |               0 |                     0 | 0/30                          |                           0 |                        30 |                               0 |
| interactive-short-1    | 30/30               |                 0 |               0 |                     0 | 0/30                          |                           0 |                        30 |                               0 |
| interactive-short-2    | 0/30                |                 0 |               0 |                    30 | 0/30                          |                           0 |                         0 |                              30 |
| interactive-short-3    | 0/30                |                30 |               0 |                     0 | 0/30                          |                          30 |                         0 |                               0 |
| interactive-short-4    | 30/30               |                 0 |               0 |                     0 | 30/30                         |                           0 |                         0 |                               0 |
| interactive-short-5    | 30/30               |                 0 |               0 |                     0 | 30/30                         |                           0 |                         0 |                               0 |
| interactive-short-6    | 0/30                |                30 |               0 |                     0 | 0/30                          |                          30 |                         0 |                               0 |
| interactive-short-7    | 0/30                |                30 |               0 |                     0 | 0/30                          |                          30 |                         0 |                               0 |

## How the numbers are aggregated

Every summary below collapses the runs in two stages: the median over the replications of one instance, then the geometric mean over the instances of a template. Replications differ by run noise, which a median absorbs; instances differ by orders of magnitude, and a geometric mean weighs a 10x-slower instance as 10x rather than letting it dominate the way an arithmetic mean would. Equal weight per instance means an engine cannot move a template's summary by failing more often on the hard instance.

Read the next section before trusting any template-level number.

## Do the instances of a template behave alike?

Mostly not. `instance_share` is the fraction of log-scale spread that lies between the instances of a template rather than between replications of one instance; `spread_factor` is the slowest instance median over the fastest, and `run_noise_factor` the same spread within one instance. Where the first dwarfs the second, more replications buy nothing -- the uncertainty is in which constants the template was bound to, not in the measurement.

| template               | engine            |   instances |   instance_share |   spread_factor |   run_noise_factor |   slowest_instance |   fastest_instance |
|:-----------------------|:------------------|------------:|-----------------:|----------------:|-------------------:|-------------------:|-------------------:|
| interactive-discover-1 | default           |           5 |            0.72  |            2.02 |               1.27 |                  0 |                  2 |
| interactive-discover-1 | derived-resources |           5 |            0.434 |            1.57 |               1.32 |                  0 |                  2 |
| interactive-discover-2 | default           |           5 |            0.985 |            2.46 |               1.05 |                  0 |                  2 |
| interactive-discover-3 | default           |           5 |            0.68  |            2.01 |               1.19 |                  3 |                  2 |
| interactive-discover-4 | default           |           5 |            0.812 |            1.93 |               1.17 |                  4 |                  2 |
| interactive-discover-5 | default           |           5 |            0.675 |            1.64 |               1.17 |                  0 |                  3 |
| interactive-discover-5 | derived-resources |           5 |            0.7   |            1.43 |               1.14 |                  0 |                  1 |
| interactive-discover-6 | default           |           4 |            0.995 |           88.08 |               1.15 |                  3 |                  2 |
| interactive-discover-6 | derived-resources |           5 |            1     |          100.72 |               1.05 |                  0 |                  2 |
| interactive-discover-7 | default           |           3 |            0.989 |            3.89 |               1.07 |                  4 |                  2 |
| interactive-discover-7 | derived-resources |           3 |            0.495 |            1.62 |               1.3  |                  4 |                  2 |
| interactive-discover-8 | default           |           5 |            0.983 |            6.29 |               1.11 |                  3 |                  1 |
| interactive-short-1    | default           |           5 |            0.333 |            1.44 |               1.37 |                  0 |                  3 |
| interactive-short-4    | default           |           5 |            0.852 |            2.59 |               1.24 |                  3 |                  0 |
| interactive-short-4    | derived-resources |           5 |            0.924 |            2.9  |               1.16 |                  3 |                  0 |
| interactive-short-5    | default           |           5 |            0.999 |           45.47 |               1.03 |                  2 |                  3 |
| interactive-short-5    | derived-resources |           5 |            0.302 |            1.92 |               1.78 |                  2 |                  3 |

### Does the engine comparison survive per instance?

The template-level ratio recomputed on each instance separately. A row marked `straddles_break_even` is one where the engines trade wins instance by instance, so the single ratio is an average over a disagreement, not a direction.

| template               | engine            |   instances |   ratio_geomean |   ratio_min |   ratio_max | direction_agrees   | straddles_break_even   |
|:-----------------------|:------------------|------------:|----------------:|------------:|------------:|:-------------------|:-----------------------|
| interactive-discover-1 | derived-resources |           5 |            0.89 |        0.71 |        1.05 | 3/5                | yes                    |
| interactive-discover-5 | derived-resources |           5 |            1.01 |        0.9  |        1.13 | 3/5                | yes                    |
| interactive-discover-6 | derived-resources |           4 |            0.67 |        0.5  |        0.92 | 4/4                | no                     |
| interactive-discover-7 | derived-resources |           3 |            0.77 |        0.46 |        1.11 | 2/3                | yes                    |
| interactive-short-4    | derived-resources |           5 |            1.11 |        1.06 |        1.19 | 5/5                | no                     |
| interactive-short-5    | derived-resources |           5 |            0.24 |        0.05 |        1.25 | 4/5                | yes                    |

### Which engine wins each individual instance

| template               |   instances_compared |   wins default |   wins derived-resources | unanimous   | per_instance_winner                                                                           |
|:-----------------------|---------------------:|---------------:|-------------------------:|:------------|:----------------------------------------------------------------------------------------------|
| interactive-discover-1 |                    5 |              2 |                        3 | no          | 0:derived-resources, 1:default, 2:default, 3:derived-resources, 4:derived-resources           |
| interactive-discover-5 |                    5 |              3 |                        2 | no          | 0:derived-resources, 1:derived-resources, 2:default, 3:default, 4:default                     |
| interactive-discover-6 |                    4 |              0 |                        4 | yes         | 1:derived-resources, 2:derived-resources, 3:derived-resources, 4:derived-resources            |
| interactive-discover-7 |                    3 |              1 |                        2 | no          | 1:derived-resources, 2:default, 4:derived-resources                                           |
| interactive-short-4    |                    5 |              5 |                        0 | yes         | 0:default, 1:default, 2:default, 3:default, 4:default                                         |
| interactive-short-5    |                    5 |              1 |                        4 | no          | 0:derived-resources, 1:derived-resources, 2:derived-resources, 3:default, 4:derived-resources |

## Per-template performance (completed runs only -- survivorship-biased)

`geomean` is the two-stage aggregate, `pooled_median` the single-stage median over all runs at once. Where the two disagree, the template is a mixture of instances and the table above says by how much.

| template               | geomean default   | pooled_median default   | instance_range default   | geo_sd default   | geomean derived-resources   | pooled_median derived-resources   | instance_range derived-resources   | geo_sd derived-resources   | vs_default derived-resources   |
|:-----------------------|:------------------|:------------------------|:-------------------------|:-----------------|:----------------------------|:----------------------------------|:-----------------------------------|:---------------------------|:-------------------------------|
| interactive-discover-1 | 1749.4            | 1646.0                  | 1264-2556                | 1.41             | 1554.0                      | 1559.5                            | 1334-2091                          | 1.23                       | 0.89                           |
| interactive-discover-2 | 1737.4            | 1681.5                  | 1116-2746                | 1.5              | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-discover-3 | 109969.1          | 103117.0                | 81558-163708             | 1.3              | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-discover-4 | 1658.3            | 1638.5                  | 1207-2332                | 1.35             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-discover-5 | 1313.5            | 1284.5                  | 1051-1728                | 1.22             | 1325.8                      | 1238.5                            | 1156-1658                          | 1.18                       | 1.01                           |
| interactive-discover-6 | 6413.7            | 2641.0                  | 1528-134626              | 7.79             | 8412.0                      | 1736.5                            | 1241-124996                        | 11.72                      | 1.31                           |
| interactive-discover-7 | 2899.0            | 2508.5                  | 1580-6145                | 1.99             | 2226.1                      | 2207.0                            | 1759-2842                          | 1.27                       | 0.77                           |
| interactive-discover-8 | 16684.3           | 18742.0                 | 7267-45721               | 2.25             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-short-1    | 1207.5            | 1280.0                  | 978-1406                 | 1.15             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-short-2    | <NA>              | <NA>                    | -                        | <NA>             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-short-3    | <NA>              | <NA>                    | -                        | <NA>             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-short-4    | 312.3             | 236.0                   | 218-564                  | 1.58             | 347.1                       | 267.5                             | 231-669                            | 1.65                       | 1.11                           |
| interactive-short-5    | 6975.7            | 5646.0                  | 1011-45971               | 4.02             | 1666.2                      | 1594.0                            | 1262-2422                          | 1.29                       | 0.24                           |
| interactive-short-6    | <NA>              | <NA>                    | -                        | <NA>             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-short-7    | <NA>              | <NA>                    | -                        | <NA>             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |

## Time to last result

| template               | geomean default   | pooled_median default   | instance_range default   | geo_sd default   | geomean derived-resources   | pooled_median derived-resources   | instance_range derived-resources   | geo_sd derived-resources   | vs_default derived-resources   |
|:-----------------------|:------------------|:------------------------|:-------------------------|:-----------------|:----------------------------|:----------------------------------|:-----------------------------------|:---------------------------|:-------------------------------|
| interactive-discover-1 | 779.2             | 587.0                   | 465-2454                 | 1.99             | 796.6                       | 790.5                             | 777-848                            | 1.04                       | 1.02                           |
| interactive-discover-2 | 1421.5            | 1659.0                  | 769-2746                 | 1.68             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-discover-3 | 109968.1          | 103117.0                | 81558-163707             | 1.3              | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-discover-4 | 1658.0            | 1638.0                  | 1207-2332                | 1.35             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-discover-5 | 1003.8            | 979.0                   | 676-1369                 | 1.35             | 795.8                       | 781.5                             | 743-854                            | 1.06                       | 0.79                           |
| interactive-discover-6 | 1896.5            | 1922.5                  | 1290-3226                | 1.56             | 1294.5                      | 1179.0                            | 1126-1599                          | 1.17                       | 0.68                           |
| interactive-discover-7 | 2268.6            | 2223.5                  | 1411-3722                | 1.62             | 1967.3                      | 2046.5                            | 1652-2204                          | 1.17                       | 0.87                           |
| interactive-discover-8 | 15902.1           | 17887.0                 | 6818-43926               | 2.27             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-short-1    | 335.0             | 335.5                   | 324-343                  | 1.02             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-short-2    | <NA>              | <NA>                    | -                        | <NA>             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-short-3    | <NA>              | <NA>                    | -                        | <NA>             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-short-4    | 129.7             | 124.0                   | 106-164                  | 1.21             | 140.3                       | 130.0                             | 114-190                            | 1.24                       | 1.08                           |
| interactive-short-5    | 384.1             | 365.0                   | 338-438                  | 1.13             | 869.5                       | 871.0                             | 865-882                            | 1.01                       | 2.26                           |
| interactive-short-6    | <NA>              | <NA>                    | -                        | <NA>             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |
| interactive-short-7    | <NA>              | <NA>                    | -                        | <NA>             | <NA>                        | <NA>                              | -                                  | <NA>                       | <NA>                           |

## Per-template timing, matched instances only

Restricted to the (template, instance) pairs every engine completed, so the engines are compared on the same queries. `instances_used` versus `instances_total` says how much of the workload each row rests on.

| template               |   instances_used |   instances_total | geomean default   | instance_range default   | geomean derived-resources   | instance_range derived-resources   | vs_default derived-resources   |
|:-----------------------|-----------------:|------------------:|:------------------|:-------------------------|:----------------------------|:-----------------------------------|:-------------------------------|
| interactive-discover-1 |                5 |                 5 | 1749.4            | 1264-2556                | 1554.0                      | 1334-2091                          | 0.89                           |
| interactive-discover-2 |                0 |                 5 | <NA>              | -                        | <NA>                        | -                                  | <NA>                           |
| interactive-discover-3 |                0 |                 5 | <NA>              | -                        | <NA>                        | -                                  | <NA>                           |
| interactive-discover-4 |                0 |                 5 | <NA>              | -                        | <NA>                        | -                                  | <NA>                           |
| interactive-discover-5 |                5 |                 5 | 1313.5            | 1051-1728                | 1325.8                      | 1156-1658                          | 1.01                           |
| interactive-discover-6 |                4 |                 5 | 6413.7            | 1528-134626              | 4284.5                      | 1241-123373                        | 0.67                           |
| interactive-discover-7 |                3 |                 5 | 2899.0            | 1580-6145                | 2226.1                      | 1759-2842                          | 0.77                           |
| interactive-discover-8 |                0 |                 5 | <NA>              | -                        | <NA>                        | -                                  | <NA>                           |
| interactive-short-1    |                0 |                 5 | <NA>              | -                        | <NA>                        | -                                  | <NA>                           |
| interactive-short-2    |                0 |                 5 | <NA>              | -                        | <NA>                        | -                                  | <NA>                           |
| interactive-short-3    |                0 |                 5 | <NA>              | -                        | <NA>                        | -                                  | <NA>                           |
| interactive-short-4    |                5 |                 5 | 312.3             | 218-564                  | 347.1                       | 231-669                            | 1.11                           |
| interactive-short-5    |                5 |                 5 | 6975.7            | 1011-45971               | 1666.2                      | 1262-2422                          | 0.24                           |
| interactive-short-6    |                0 |                 5 | <NA>              | -                        | <NA>                        | -                                  | <NA>                           |
| interactive-short-7    |                0 |                 5 | <NA>              | -                        | <NA>                        | -                                  | <NA>                           |

## PAR-2 (failures penalised, not dropped)

A run that never finished counts as 2x the 300s budget. An engine cannot look fast here by failing more often. Read alongside completion.

| template               |   par2 default |   par2 derived-resources |   vs_default derived-resources |
|:-----------------------|---------------:|-------------------------:|-------------------------------:|
| interactive-discover-1 |         2052.6 |                   1835   |                           0.89 |
| interactive-discover-2 |         1873.6 |                 600000   |                         320.23 |
| interactive-discover-3 |       132971   |                 600000   |                           4.51 |
| interactive-discover-4 |         1841.7 |                 600000   |                         325.78 |
| interactive-discover-5 |         1400.4 |                   1405.7 |                           1    |
| interactive-discover-6 |       179544   |                  50684.6 |                           0.28 |
| interactive-discover-7 |       242022   |                 241506   |                           1    |
| interactive-discover-8 |        21465.7 |                 600000   |                          27.95 |
| interactive-short-1    |         1446.4 |                 600000   |                         414.81 |
| interactive-short-2    |       600000   |                 600000   |                           1    |
| interactive-short-3    |       600000   |                 600000   |                           1    |
| interactive-short-4    |          380.5 |                    408   |                           1.07 |
| interactive-short-5    |        14051.8 |                   2950.5 |                           0.21 |
| interactive-short-6    |       600000   |                 600000   |                           1    |
| interactive-short-7    |       600000   |                 600000   |                           1    |

## Setup cost, streaming, and the tail

Each run split into three phases: reaching the first result, streaming the rest, and whatever happens after the last result has arrived. The middle phase is nearly empty in this dataset -- results arrive in a burst -- so `after_last_result` is where the time that is not startup actually goes, and an engine can deliver every answer early and still finish late.

| template               |   instances_used |   to_first_result default |   to_last_result default |   streaming_span default |   after_last_result default |   to_first_result derived-resources |   to_last_result derived-resources |   streaming_span derived-resources |   after_last_result derived-resources |   startup_delta_ms derived-resources |   to_last_ratio derived-resources |
|:-----------------------|-----------------:|--------------------------:|-------------------------:|-------------------------:|----------------------------:|------------------------------------:|-----------------------------------:|-----------------------------------:|--------------------------------------:|-------------------------------------:|----------------------------------:|
| interactive-discover-1 |                5 |                     567.5 |                    779.2 |                    211.7 |                       970.2 |                               795.8 |                              796.6 |                                0.8 |                                 757.4 |                                228.3 |                              1.02 |
| interactive-discover-5 |                5 |                     571.9 |                   1003.8 |                    431.9 |                       309.7 |                               756.6 |                              795.8 |                               39.2 |                                 529.9 |                                184.7 |                              0.79 |
| interactive-discover-6 |                4 |                    1609.7 |                   1896.5 |                    286.8 |                      4517.2 |                              1191.3 |                             1227.9 |                               36.6 |                                3056.6 |                               -418.4 |                              0.65 |
| interactive-discover-7 |                3 |                    2268.6 |                   2268.6 |                      0   |                       630.4 |                              1967.3 |                             1967.3 |                                0   |                                 258.8 |                               -301.3 |                              0.87 |
| interactive-short-4    |                5 |                     129.7 |                    129.7 |                      0   |                       182.6 |                               140.3 |                              140.3 |                                0   |                                 206.9 |                                 10.6 |                              1.08 |
| interactive-short-5    |                5 |                     384.1 |                    384.1 |                      0   |                      6591.5 |                               869.5 |                              869.5 |                                0   |                                 796.7 |                                485.3 |                              2.26 |

## Progress and throughput

`median_delivered` and `from_failed_runs` count partial output from runs that timed out or crashed; throughput is over completed runs only.

| template               |   median_delivered default | from_failed_runs default   | median_throughput_per_s default   |   median_delivered derived-resources | from_failed_runs derived-resources   | median_throughput_per_s derived-resources   |
|:-----------------------|---------------------------:|:---------------------------|:----------------------------------|-------------------------------------:|:-------------------------------------|:--------------------------------------------|
| interactive-discover-1 |                          6 | -                          | 2.9                               |                                    6 | -                                    | 3.02                                        |
| interactive-discover-2 |                         66 | -                          | 36.16                             |                                   66 | 2640 over 30 runs                    | <NA>                                        |
| interactive-discover-3 |                         68 | 0 over 1 runs              | 0.67                              |                                   68 | 3126 over 30 runs                    | <NA>                                        |
| interactive-discover-4 |                          3 | -                          | 2.28                              |                                    3 | 126 over 30 runs                     | <NA>                                        |
| interactive-discover-5 |                          4 | -                          | 3.81                              |                                    4 | -                                    | 3.36                                        |
| interactive-discover-6 |                          2 | 202 over 8 runs            | 0.63                              |                                    2 | -                                    | 0.79                                        |
| interactive-discover-7 |                          1 | 15 over 12 runs            | 0.4                               |                                    1 | 24 over 12 runs                      | 0.45                                        |
| interactive-discover-8 |                         10 | -                          | 0.53                              |                                   10 | 300 over 30 runs                     | <NA>                                        |
| interactive-short-1    |                          1 | -                          | 0.78                              |                                    1 | 30 over 30 runs                      | <NA>                                        |
| interactive-short-2    |                          0 | 0 over 30 runs             | <NA>                              |                                    0 | 0 over 30 runs                       | <NA>                                        |
| interactive-short-3    |                          0 | 3 over 30 runs             | <NA>                              |                                   14 | 387 over 30 runs                     | <NA>                                        |
| interactive-short-4    |                          1 | -                          | 4.24                              |                                    1 | -                                    | 3.74                                        |
| interactive-short-5    |                          1 | -                          | 0.18                              |                                    1 | -                                    | 0.63                                        |
| interactive-short-6    |                          0 | 12 over 30 runs            | <NA>                              |                                    0 | 12 over 30 runs                      | <NA>                                        |
| interactive-short-7    |                          0 | 0 over 30 runs             | <NA>                              |                                    0 | 0 over 30 runs                       | <NA>                                        |

## Errors

| engine            | error                                                                                                          |   runs | templates                                                                                      |
|:------------------|:---------------------------------------------------------------------------------------------------------------|-------:|:-----------------------------------------------------------------------------------------------|
| default           | Unexpected "!" at position 0 in state STOP                                                                     |    101 | discover-3, discover-6, discover-7, short-3, short-6, short-7                                  |
| default           | Invalid SPARQL endpoint response from http://localhost:3001/sparql (HTTP status 400): Query operation process… |     30 | short-2                                                                                        |
| default           | terminated                                                                                                     |     10 | short-3, short-7                                                                               |
| derived-resources | Unexpected "!" at position 0 in state STOP                                                                     |    176 | discover-2, discover-3, discover-4, discover-7, discover-8, short-1, short-3, short-6, short-7 |
| derived-resources | Invalid SPARQL endpoint response from http://localhost:3001/sparql (HTTP status 400): Query operation process… |     30 | short-2                                                                                        |
| derived-resources | Unexpected "!" at position 456 in state STOP                                                                   |     12 | discover-4                                                                                     |
| derived-resources | Unexpected "!" at position 455 in state STOP                                                                   |      6 | discover-4                                                                                     |
| derived-resources | Unexpected "!" at position 10139 in state STOP                                                                 |      5 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 10524 in state STOP                                                                 |      5 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 1058 in state STOP                                                                  |      5 | discover-4                                                                                     |
| derived-resources | Unexpected "!" at position 320 in state STOP                                                                   |      5 | discover-8                                                                                     |
| derived-resources | Unexpected "!" at position 559 in state STOP                                                                   |      5 | discover-8                                                                                     |
| derived-resources | Unexpected "!" at position 390 in state STOP                                                                   |      4 | discover-8                                                                                     |
| derived-resources | Unexpected "!" at position 8368 in state STOP                                                                  |      4 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 404 in state STOP                                                                   |      3 | discover-8                                                                                     |
| derived-resources | Unexpected "!" at position 158 in state STOP                                                                   |      2 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 761 in state STOP                                                                   |      2 | discover-4                                                                                     |
| derived-resources | Unexpected "!" at position 11177 in state STOP                                                                 |      1 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 1137 in state STOP                                                                  |      1 | discover-8                                                                                     |
| derived-resources | Unexpected "!" at position 12409 in state STOP                                                                 |      1 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 152 in state STOP                                                                   |      1 | discover-4                                                                                     |
| derived-resources | Unexpected "!" at position 1523 in state STOP                                                                  |      1 | discover-8                                                                                     |
| derived-resources | Unexpected "!" at position 16164 in state STOP                                                                 |      1 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 17268 in state STOP                                                                 |      1 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 18012 in state STOP                                                                 |      1 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 21059 in state STOP                                                                 |      1 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 2169 in state STOP                                                                  |      1 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 3846 in state STOP                                                                  |      1 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 4009 in state STOP                                                                  |      1 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 478 in state STOP                                                                   |      1 | discover-8                                                                                     |
| derived-resources | Unexpected "!" at position 4975 in state STOP                                                                  |      1 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 570 in state STOP                                                                   |      1 | discover-8                                                                                     |
| derived-resources | Unexpected "!" at position 8051 in state STOP                                                                  |      1 | discover-3                                                                                     |
| derived-resources | Unexpected "!" at position 8918 in state STOP                                                                  |      1 | discover-3                                                                                     |
| derived-resources | terminated                                                                                                     |      1 | short-6                                                                                        |

## Figures

- `output-v2-limit-rate/figures/time_ms-by-template-facets-light.png`
- `output-v2-limit-rate/figures/time_ms-by-template-facets-dark.png`
- `output-v2-limit-rate/figures/time_ms-by-template-single-light.png`
- `output-v2-limit-rate/figures/time_ms-by-template-single-dark.png`
- `output-v2-limit-rate/figures/http_requests-by-template-facets-light.png`
- `output-v2-limit-rate/figures/http_requests-by-template-facets-dark.png`
- `output-v2-limit-rate/figures/http_requests-by-template-single-light.png`
- `output-v2-limit-rate/figures/http_requests-by-template-single-dark.png`
- `output-v2-limit-rate/figures/first_result_ms-by-template-facets-light.png`
- `output-v2-limit-rate/figures/first_result_ms-by-template-facets-dark.png`
- `output-v2-limit-rate/figures/first_result_ms-by-template-single-light.png`
- `output-v2-limit-rate/figures/first_result_ms-by-template-single-dark.png`
- `output-v2-limit-rate/figures/last_result_ms-by-template-facets-light.png`
- `output-v2-limit-rate/figures/last_result_ms-by-template-facets-dark.png`
- `output-v2-limit-rate/figures/last_result_ms-by-template-single-light.png`
- `output-v2-limit-rate/figures/last_result_ms-by-template-single-dark.png`
- `output-v2-limit-rate/figures/throughput_per_s-by-template-facets-light.png`
- `output-v2-limit-rate/figures/throughput_per_s-by-template-facets-dark.png`
- `output-v2-limit-rate/figures/throughput_per_s-by-template-single-light.png`
- `output-v2-limit-rate/figures/throughput_per_s-by-template-single-dark.png`
- `output-v2-limit-rate/figures/instance-spread-time_ms-light.png`
- `output-v2-limit-rate/figures/instance-variance-share-light.png`
- `output-v2-limit-rate/figures/completion-by-template-light.png`
- `output-v2-limit-rate/figures/result-arrival-curves-light.png`
- `output-v2-limit-rate/figures/speedup-vs-query-cost-light.png`
- `output-v2-limit-rate/figures/instance-spread-time_ms-dark.png`
- `output-v2-limit-rate/figures/instance-variance-share-dark.png`
- `output-v2-limit-rate/figures/completion-by-template-dark.png`
- `output-v2-limit-rate/figures/result-arrival-curves-dark.png`
- `output-v2-limit-rate/figures/speedup-vs-query-cost-dark.png`
