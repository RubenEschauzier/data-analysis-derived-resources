# Composite derived resources on FedShop: investigation notes

Working notes, 2026-11-20 to 2026-11-23. Goal: find out why composite derived resources show no benefit in
result arrival and throughput on FedShop compared with `derived-pattern-only`, and what would make the benefit
appear. Runtime matters less than arrival.

Status: nothing below is committed. Numbers marked *pending* are from runs still in progress.

---

## 1. Summary

1. **Discovery is bounded by document crawling, with the engine and the single Solid server both near one core.**
   One CSS process serves the documents of all 140 pods; Virtuoso is near 0%. A document waits 110–160 ms
   locally and about 560 ms on the VM before the server answers. *Revised 2026-11-23:* with 700 CPU samples over
   36 runs, the engine (capped at one core) sits at 93–98% while CSS is at about 80% (p90 120%), so locally the
   engine is at least as binding as CSS (the earlier 67–75% engine figure came from a few samples). `-w 4` was
   silently ignored by the benchmark's CSS config, so more CSS processes are still untested. See §4.7.
2. **The "20–27 s composite lag" on the VM is not server time.** Composite and pattern SPARQL requests take about
   20–30 ms on the VM too. The time goes to discovering the pod (q12's answer pod is first reached at 10–12 s),
   then 2.5–3 s before its requests leave, then 1.2–2.4 s before the result appears. The storage-priority fix,
   which helped locally, makes no difference on the VM (verified mounted): there the pod is reached after
   ~200–240 documents at ~20 per second. See §4.7.
3. **Query shape.** The selective constant (product type) sits in the producer pod. Offers and reviews are reached
   through object positions (`?listing fs:listingOf ?product`) and carry no constant, so their composites ship
   about 99% rows that never join (q16: 81 of 9,986 offers, 540 of 53,637 reviews). A composite is then the same
   data as its patterns, fetched at the same time from a fast server, and saves nothing on the critical path.
   See §4.2.
4. **Engine: composites as eddy operators duplicated work** (1.4–1.9× the probes of pattern-only). Virtual
   composites (a composite as an extra index on the base SteMs it covers) bring probes below pattern-only and
   remove derived's q16 regression, but arrival is at best on par with pattern-only. See §4.3.
5. **Correctness gap, fixed:** chain composites could produce duplicate results when a composite registers while
   the query runs (the chain-claim bug). Fixed with a timestamp rule. This needs a subsection in the paper
   (TODO added). See §4.4.
6. **Bound (bind-join-like) composites** request a composite only for the values its seed (a composite with a
   constant) produces, in batches with one request in flight per endpoint. Implemented and correct on q16; 100×
   less composite data, and total SPARQL bytes back at pattern-only level. Arrival: no robust benefit (small hints
   on q01 and q13 first/half results; q16 half and last 30–60% slower). See §4.6. Pure one-value-per-request bind join loses
   clearly; batching values per request is what makes binding pay (§4.5).

---

## 2. Setups

| | Local | VM (`vw-fedshop` = `n064-01.wall2`, slice "expres") |
|---|---|---|
| CPU | i7-11700KF, 3.6–5.0 GHz, 16 threads | Xeon E5-2650 v2, 2.6 GHz (2013), 32 threads |
| Engine CPU cap | `--cpus 1` | `cpu_percentage: 100` (1 core) |
| Per-core speed | | about 2.5–3× slower than local |
| Proxy | generator `38166e0…`: passthrough, request log with `headers_ms` | generator `c9226c…`: document requests limited to 64 at once, request log without `headers_ms` |
| Storage-priority fix | mounted (§4.1) | only in the diagnosis run's combinations 2–3 |
| HTTP delay (`ActorHttpDelay`, `ccqs:config/http/actors-delay.json`, 80 ± 10 ms before every request) | **none**: the local images (built 2026-11-17) carry an expanded `/tmp/config.json` without the import | **yes**: the images import `configs-fedshop/config-fedshop-discovery-*-hybrid-federation*.json`, which import it |

**Every local comparison in this document ran without the experiment's HTTP delay** (found 2026-11-23). The delay
is a `setTimeout` before each request, with no limit on parallel requests (`http/actors-no-limit.json`), so
parallel requests wait side by side: it adds 80 ms per *dependent* round trip, not per request. It therefore
does not penalise pattern-only's many parallel pattern requests against one composite, but it does penalise
bound composites (one extra dependent round trip per pod) and every step of traversal (document → link →
document). To reproduce the experiment locally, run the images with the client config of
`input/configs/config-client-*.json`, or mount it over `/tmp/config.json`.

VM experiment directories:

* `~/jbr-experiment-fedshop-discovery-full`: full run of 17–19 Nov (derived, pattern-only, adaptive-only).
  Untouched.
* `~/fedshop-lag-diagnosis`: copy for the diagnosis run of 2026-11-23. q12 and q16 instance 0, request log on,
  derived and pattern-only, each with and without the storage fix (fix bind-mounted via `additionalBinds`). Uses
  copies of the original's Virtuoso volumes, because the volume name is a hash of the experiment's path.

---

## 3. Benchmark and setup changes (record in the experiment README)

* Proxy: passthrough, request logging, CPU caps per container (earlier in the session).
* Tracking experiment: compares only `derived` and `derived-pattern-only`.
* q02, q03: removed OPTIONALs without matches and FILTERs that blocked streaming (in the README).
* **2026-11-23: storage-priority fix** (§4.1), added to the `jbr-experiment-fedshop-discovery-enable-proxy-tracking`
  README, as a bind-mounted override (`input/overrides/…`, `additionalBinds`). The client image's build context
  only holds the client config, so the file cannot be copied in.
* *Proposed:* CSS with worker processes (`-w`), see §6.

---

## 4. Findings

### 4.1 Discovery: storage-priority bug (fix validated locally; no effect on the VM, §4.7)

Producer brand documents state `pim:storage <./>` before `void:inDataset <./>`. The Solid storage extractor
queues the storage-root link without priority, and the prioritised `void:inDataset` link to the same document
is then dropped as already queued. A producer's dataset document (which names its SPARQL service) therefore
waits about 10–11 s instead of about 0.3 s. Adding `pim:storage` to `derivedResourcePredicates` in
`wrapper-prioritize-derived-resources-and-datasets.json` brings endpoint contact from 11–16 s to about 3.5 s
locally. On its own, it barely changed result arrival.

Fixed in the engine config (`comunica-feature-link-traversal-adaptive-derived-resources`, needs an image
rebuild) and as an override in the tracking experiment.

### 4.2 Why composites show no benefit: workload and query shape

* No "best case" template exists. q03 and q07 were gated by OPTIONAL with FILTER(!bound); q04 and q05 span
  publishers.
* Every analytical query has the shape: a selective constant in the producer pod, reached through object
  positions from blocks without a constant at vendors and review sites.

Selectivity, counted on the local Virtuoso (all data):

| product type (query) | products | offers needed | reviews needed |
|---|---|---|---|
| 155 (q16) | 219 | 81 / 9,986 (0.8%) | 540 / 53,637 (1.0%) |
| 142 (q01) | 137 | 48 / 9,986 (0.5%) | 244 / 53,637 (0.5%) |
| 322 (q14) | 356 | 128 / 9,986 (1.3%) | 623 / 53,637 (1.2%) |

Query used: `SELECT (COUNT(DISTINCT ?o) AS ?n) WHERE { ?o bsbm:product ?l . ?l fs:listingOf ?p . ?p rdf:type <…/ProductType155#it> }`
against `http://<fedshop-virtuoso>:8890/sparql`, and likewise for reviews (`bsbm:reviewFor`).

What a composite can save, and why none of it is on the critical path here:

| saving | why it does not apply |
|---|---|
| fewer requests | pattern requests are parallel, and Virtuoso answers in about 14 ms |
| fewer bytes | the composite is as unselective as its patterns |
| less client join work | a star join on the subject is cheap; the expensive joins cross pods through object positions |
| earlier complete rows | a composite is discovered together with its patterns, and discovery is slow (§4.7) |

### 4.3 Engine variants (local, 2026-11-22, instance 0, median of 3, storage fix in all)

Seconds until 50% of the rows had arrived:

| query | pattern-only | derived | virtual | virtual, no drain | claim-directed |
|---|---|---|---|---|---|
| q01 | 9.2 | 8.9 | 9.1 | 9.3 | 9.9 |
| q06 | 8.0 | 8.6 | 8.0 | 8.4 | 9.1 |
| q12 (1 row) | 3.3 | 5.1 | 4.0 | 4.1 | 5.1 |
| q13 | **4.8** | 6.8 | 6.8 | 6.3 | 6.0 |
| q14 | 12.0 | 11.6 | **10.9** | 11.4 | 11.6 |
| q16 | **15.3** | 24.2 | 18.8 | 17.9 | 23.5 |

q16 probes: pattern-only 488k, derived 928k, virtual 366k, no drain 361k, claim-directed 631k.

* Reading composites first (drain) plus unbounded union buffers: no gain.
* Claim-directed routing (composites stay eddy operators; copies the claim rules out are skipped) removes about
  30% of derived's probes, but cannot decide object-joined stars, whose anchors are unbound at the split.
* Earlier hypothesis withdrawn: the composite-source actor's `await responded` does not delay SPARQL-endpoint
  composites. Only template resources set `responded`. q13's lag behind pattern-only is still unexplained.

### 4.4 Correctness

* **Chain-claim bug (fixed 2026-11-23).**
  * *The bug:* for a chain block, only patterns binding all anchors got the base filter. A block solution whose
    base parts were stored partly before and partly after the composite registered was produced twice: once by
    the composite and once by the base operators.
  * *The fix:* the base route produces a claimed solution only if *all* its parts were stored before the
    registration timestamp τ; the composite's row is pruned in exactly that case. Results carry per-part
    timestamps; the controller filters when some covered pattern cannot decide on storage.
  * *Tests:* `StemsClaimRouting-test.ts` with stars, chains and bound requests; 86 tests pass over 3,000 seeds.
* q13's "99 vs 100 rows" is not a bug: one price comes back as both `xsd:integer` and `xsd:decimal`, and
  DISTINCT keeps both.
* Rare missing rows (pattern-only q16 31/58 once, virtual q01 20/21 once): an existing engine problem, not yet
  reproducible.
* Paper: TODO with a sketch added to `delegation-paper.tex`, after the Generalised Pruning lemma ("Composite
  resources registered during execution").

### 4.5 Bind join: is one request per value worth it? (local micro-benchmark)

q16's blocks against the 20 vendor and 20 review-site endpoints, Node client capped at one core, warm runs:

| block (219 products) | requests | rows | data | wall | client CPU |
|---|---|---|---|---|---|
| vendor, scan | 20 | 9,986 | 4.9 MB | 0.17 s | 35 ms |
| vendor, one value per request | 4,380 | 81 | 0.66 MB | 2.4–2.9 s | 1,400–1,600 ms |
| vendor, all values in one request (VALUES) | 20 | 81 | 43 KB | 0.01 s | 8 ms |
| review, scan | 20 | 37,505 | 19 MB | 0.48 s | 105 ms |
| review, one value per request | 4,380 | 375 | 0.77 MB | 1.6–2.0 s | 1,400 ms |
| review, all values in one request | 20 | 375 | 193 KB | 0.015 s | 8 ms |

98% of the single-value requests come back empty. Conclusion: batch the values (`scripts/bench.mjs`).

### 4.6 Bound composites (implemented 2026-11-23)

Design:

* **Partition** (`DERIVED_EXTEND_BLOCKS=1`): a block also takes the stars hanging off its object variables, and
  single-pattern blocks it absorbs are dropped. The vendor block becomes offer + `?listing fs:listingOf ?product`,
  connected to the rest of the query only through `?product`.
* **Roles** (`DERIVED_BOUND_COMPOSITES=1`):
  * A block with a constant is a *seed*; the values of its rows are collected.
  * A block without a constant that shares a variable with a seed's region is a *target*. The region is the star
    of the constant's subject, plus the stars hanging off its object variables.
* **Scheduling, per target (one pod, one block):**
  * At most one request in flight. The first goes as soon as there is a value; values found meanwhile go into
    the next request (at most 500 per request). The batch size follows the endpoint's response time, so there
    is no size or timer to tune.
  * A pod found later is sent all values so far in one request.
  * Requests use Comunica's bind-join input (`joinBindings`, sent as `VALUES`).
* **Cost decision, per newly found pod:**
  * Bind if no more than 30% of the stored tuples binding the variable match a seed value (needs at least 200
    tuples as evidence; at most 5,000 values).
  * Once unselective, pods found from then on are requested whole; pods bound before keep receiving new values.
* **Lifecycle:** traversal is kept from ending while a seed is still read or a request waits or is underway.
  The block is not accepted for the store-level drop, since it is answered only for the values sent.
* **Claims:** one per (pod, batch), with its own τ, under the same timestamp rule as §4.4.

First run, q16 locally:

* 58/58 correct rows.
* All 240 targets bound; the estimate saw about 1% (215 of 18,906 tuples).
* 376 bound requests carried 145 KB, against about 13 MB for asking the 20 discovered vendors and review sites
  whole.
* Total SPARQL bytes went from 49 MB to 38 MB.
* Arrival in single runs was noisy, so it is not reported.

Notes:

* The 20 *known* vendors and review sites are queried pattern by pattern by the federation side, not through
  composites. Only discovered pods get composites.
* Every discovered pod's endpoint is asked for every block (endpoints answer any BGP), and producers get empty
  bound requests as well.

Comparison (2026-11-23, local, instance 0, storage fix in all; P pattern-only, V virtual, X virtual + extended
blocks, B + bound composites; 6 queries, 3 rounds; `scripts/compare-bound.sh`, `scripts/analyse_bound.py`).
Medians of 3, seconds since the query was sent:

| query | cfg | first | half | last | probes | SPARQL MB | bound requests (KB) |
|---|---|---|---|---|---|---|---|
| q01 | P | 7.0 | 8.6 | 14.8 | 183k | 15.0 | |
| | V | 6.8 | 8.8 | 14.3 | 126k | 22.7 | |
| | X | 6.5 | 8.7 | 13.4 | 126k | 16.6 | |
| | B | **3.8** | **8.0** | 14.6 | 132k | 15.1 | 158 (29) |
| q06 | P | 5.8 | 7.8 | 19.9 | 207k | 13.9 | |
| | V | 7.7 | 11.2 | 19.9 | 161k | 24.9 | |
| | X | 4.8 | 7.3 | 19.0 | 164k | 18.3 | |
| | B | 4.7 | 7.3 | 19.3 | 196k | 14.0 | 0 |
| q12 | P | 4.6 | | 4.8 | 180k | 10.7 | |
| | V | 3.9 | | 4.7 | 135k | 21.7 | |
| | X | 4.6 | | 4.6 | 135k | 15.2 | |
| | B | 3.8 | | 4.8 | 170k | 10.7 | 0 |
| q13 | P | 1.8 | 6.0 | 7.0 | 238k | 15.4 | |
| | V | 2.0 | 7.1 | 7.9 | 178k | 27.9 | |
| | X | 2.0 | 7.2 | 7.8 | 184k | 21.8 | |
| | B | 1.4 | 5.8 | 7.1 | 217k | 17.5 | 120 (85) |
| q14 | P | 7.7 | 11.5 | 16.9 | 346k | 29.4 | |
| | V | 4.1 | 12.4 | 16.9 | 247k | 43.6 | |
| | X | 6.9 | 12.6 | 16.3 | 281k | 39.2 | |
| | B | 4.7 | 14.0 | 16.4 | 349k | 29.5 | 178 (77) |
| q16 | P | **12.6** | **19.4** | **27.2** | 489k | 37.5 | |
| | V | 14.3 | 29.0 | 33.5 | 357k | 59.8 | |
| | X | 14.0 | 23.6 | 31.5 | 395k | 49.3 | |
| | B | 14.2 | 31.8 | 36.8 | 454k | 37.6 | 376 (145) |

Rows: all complete (q13's 99 in V/X/B is the datatype duplicate of §4.4, the other way round).

Reading:

* **Data: bound composites remove the composite overhead.** B's SPARQL bytes equal pattern-only's (q16 37.6 vs
  37.5 MB; V 59.8), with every composite still in use.
* **First result is bimodal** (about 4 s or about 7 s in q01, q06 and q14, in every configuration, depending on
  discovery order), so 3 rounds cannot separate configurations there. Per round:
  * q01 first: P 4.3 / 7.2 / 7.0, B 3.7 / 3.8 / 5.7; q01 half: P 8.5–8.9, B 7.8–8.1 (B lower in all 3 rounds).
  * q13 first: P 1.7–2.2, B 1.3 / 1.4 / 2.2; half P 6.0–6.7, B 5.6 / 5.8 / 8.0.
  * These are the only hints of a benefit: small, and not yet significant.
* **Last result: no difference**, except q16; it is set by document-only answers (§4.7).
* **q16 regresses with every composite configuration, B the most and most consistently:** half 31.1–32.3 s vs
  P 16.7–24.0 s; last 36.1–37.1 s vs 26.1–32.5 s. Not explained yet. Candidates: the target requests wait for
  seed values (a dependent round trip per pod), more probes than V (454k vs 357k), or the engine CPU competing
  with discovery. The streamed rows of the CSS test (§6 item 2, now including B) show which answers are late.

**q16 by provenance** (`css-workers.sh`, 6 rounds of the same setup, see §4.7; row times corrected for the
runner's one-row lag, first result from the engine's time series; seconds):

| cfg | first (engine) | all: median / last | endpoint answers: median / last | document-only answers: median / last |
|---|---|---|---|---|
| P | 12.0 | 19.9 / 26.9 | 17.4 / 26.9 | 21.2 / 26.5 |
| V | 13.1 | 20.8 / 28.7 | 20.8 / 26.8 | 20.5 / 28.7 |
| B | 13.4 | 30.1 / 35.9 | 17.2 / 32.5 | **34.6** / 35.9 |

B's endpoint-backed answers arrive as early as pattern-only's at the median; its document-only answers, which
it obtains by crawling exactly as P does, arrive 13 s later. So bound composites slow the crawl itself. With
the engine at its one-core cap (§4.7), the likely cause is engine CPU spent on the bound machinery (seed taps,
per-pod target bookkeeping, 300–400 bound requests and their claims, more probes than V) taken from link
extraction and document parsing. A CPU profile of B on q16 would confirm it. q12 (one endpoint-backed row): engine
first result 6.6 s P, 6.5 s V, 7.0 s B; no difference.

**So far, no robust arrival benefit**: bound composites make composites as cheap as patterns in data, but do not
make answers arrive earlier, and q16 gets slower.

### 4.7 VM diagnosis: where the time goes

From the 17–19 Nov full run and the 2026-11-23 diagnosis run:

* **Every analytical query times out.** q01, q03, q04, q06, q12, q13, q14 and q16 hit the 180 s timeout in
  30/30 executions in all configurations. Each execution makes about 14,000 document requests (about 165 MB).
  On timeout the engine sends no statistics, so this run has no engine-side timings.
* **CPU.**
  * The engine sits at its one-core cap in 45% (derived), 43% (pattern-only) and 24% (adaptive-only) of the
    samples.
  * Virtuoso and the proxy are mostly idle.
  * jbr's `stats-*.csv` normalise CPU by the 32 cores, so a maximum of 3% is one full core.
* **Server speed.** SPARQL responses take a median of 20–30 ms, the slowest a few seconds.
* **Documents.** A document takes 560–580 ms (median) with 35–40 open at once; the old proxy's limit of 64 is
  hit in only 2% of cases. About 12,500 documents are fetched per execution, at roughly 70 per second, without
  finishing in 180 s.
* **q12** (one result, at 13.7–16.7 s derived, 15.9–19.0 s pattern-only; the answer comes from `producer64`):
  * first document of `producer64` at 10–12 s, product document at 10.8–12.6 s;
  * the SPARQL requests to it 2.5–3 s later, ending 0.2–0.7 s after that;
  * the result 1.2–2.4 s after that.
* **Storage fix on the VM: no effect** (combinations 2–3 against 0–1, q12, 3 executions each; the override was
  verified to be the only copy of the file in the image and the one the runtime config imports):

  | | first `producer64` document | documents fetched before it | its dataset document after that | its first SPARQL after that | q12 result |
  |---|---|---|---|---|---|
  | derived, as is | 10.2–11.9 s | 204–232 | +1.25–1.85 s | +2.4–3.6 s | 13.7–16.7 s |
  | derived, fix | 11.5–11.6 s | 215–241 | +1.17–2.09 s | +2.2–4.0 s | 15.7–17.6 s |
  | pattern-only, as is | 9.1–10.3 s | 223–232 | +1.41–2.05 s | +3.0–3.6 s | 15.9–19.0 s |
  | pattern-only, fix | 10.8–12.2 s | 195–224 | +1.41–1.97 s | +2.3–3.8 s | 13.4–17.3 s |

  On the VM the dataset document is not held back 10 s as it was locally; it waits 1–2 s, about two to three
  document times in a queue of 35–40 open requests. The time to the answer pod is the time to fetch ~200–240
  documents at ~20 per second. So the q12 lag is (a) ~10–12 s of document crawling before the pod is reached,
  (b) 2–4 s from its first document to its SPARQL requests (mostly the dataset document's queue wait), and
  (c) 1–2 s from the requests to the result. All three are bounded by document throughput, not by SPARQL.
  The fix is harmless and stays in.
* **Local cross-check** (new proxy, which records `headers_ms`): a document takes 131 ms, of which 130 ms pass
  before the headers. During a query, the Solid server runs at 107–128% CPU, the engine at 67–75%, and
  Virtuoso at about 0%.

**Why the Solid server is so busy even with pattern queries** (local pattern-only q16, `P-r1`):

* 13,231 documents (157 MB) are fetched; 10,716 of them are producers' product-by-month documents
  (`producerN/products/YYYY-MM`).
* **Only 100 of the 400 producers have a SPARQL endpoint.** The other 300 publish documents only. Finding their
  products of a type means crawling every product document they have.
* For producers with an endpoint, traversal is already efficient: about 2 documents each, and none requested
  after the endpoint was first queried.

**Where the answers come from** (pattern-only, round 1; producer of each answer's `?product`):

| query | answers | product from a producer with an endpoint | from a document-only producer |
|---|---|---|---|
| q16 | 58 | 38 | 20 |
| q14 | 36 | 20 | 16 |
| q06 | 26 | 12 | 14 |
| q01 | 21 | 16 | 5 |
| q12 | 1 | 1 | 0 |
| q13 | 100 | 100 | 0 |

The document-only answers can only come through crawling the Solid server, in **every** configuration
(pattern-only, derived, traversal alone). So the Solid server's throughput limits plain traversal just as much.
It sets the last-result time for q16, q14, q06 and q01 regardless of composites. Composites can only speed up
the endpoint-backed answers.

**Consequence for evaluation:** report arrival separately for endpoint-backed and document-only answers.
`scripts/run_queries_stream.py` times every result row, and `scripts/analyse_css.py` splits them.

**Solid server with workers (2026-11-23): not tested, `-w` is ignored.** The benchmark's `css-config.json`
overrides `urn:solid-server:default:Initializer` with only the logger and server initialisers, dropping the
primary/worker initialisers through which `ClusterManager` forks workers. `-w 4` therefore started one process
(checked with `docker top`), and the "W1" and "W4" phases of `css-workers.sh` ran the same setup. Enabling workers
needs the config to keep CSS's default initialiser sequence (`css:config/app/main/default.json`); the memory
key-value store and void locker are fine for read-only serving. That is a change to the generator image, to be
recorded in the README if adopted.

CPU over those 36 runs (`docker stats` every 2 s, by run): engine p50 93–98% of its one-core cap in every
configuration; CSS p50 79–83%, p90 117–122%. So locally the engine is CPU-bound too, and the earlier claim that
it idles at 67–75% does not hold. Composite work therefore competes with crawling for the engine's one core,
and an engine-side cost (more probes, bound bookkeeping) delays document-only answers (see §4.6).

Conclusion: discovery is bounded by document crawling, with both the single Solid server process and the
engine's core near saturation locally. Prioritising composite work in V8 or Node is not possible (no task
priorities), but scheduling it differently inside the engine could matter. On the VM the engine is CPU-bound
part of the time as well, on slower cores.

### 4.8 Where the engine's CPU goes (q16, local, 2026-11-23)

In-process sampling profiler (`scripts/profile_run.py`, preloads `scripts/prof/hook.js`, summarised with
`scripts/analyse_prof.py`). Window 1 = the first 30 s of the query (all answers but the last few), self time:

| | P pattern-only | V virtual | B bound |
|---|---|---|---|
| busy / wall | 29.9 / 32.0 s | 31.4 / 33.5 s | 30.0 / 32.0 s |
| garbage collection | 5.0 s (17%) | 6.1 s (19%) | 4.7 s (16%) |
| SPARQL parsing (`@traqula`) | 4.4 s (15%) | 4.4 s (14%) | 4.3 s (14%) |
| document parsing (`n3`) | 2.9 s (10%) | 2.7 s (9%) | 2.8 s (9%) |
| indexing triples (`rdf-streaming-store`, aggregated store) | 2.8 s (9%) | 2.5 s (8%) | 2.4 s (8%) |
| **join** (stems actor, bindings, `immutable`) | **2.6 s (9%)** | **2.2 s (7%)** | **4.5 s (15%)** |
| iterators and streams | 2.8 s | 2.5 s | 2.3 s |

After window 1 (crawling the rest): P busy 35.1 s, V 33.9 s, B 47.0 s, of which the join 1.3 s, 2.3 s and
5.6 s+, and GC 9.5 s, 8.6 s and 13.4 s.

Reading:

* **The join is under a tenth of the engine's CPU.** The engine's time goes to traversal: parsing and indexing
  13,000 documents, the garbage this creates, iterators, and SPARQL handling. Offloading joins to Virtuoso can
  save at most the join's share, and composites offload only the intra-pod star joins (the cross-pod joins
  product–offer–review stay in the engine, since no endpoint holds both sides). V saves 0.4 s of CPU in 30 s.
* **Composites add work rather than replace it.** V sends more SPARQL requests than P (2,580 vs 1,980) and
  more bytes (59.8 vs 37.5 MB): base patterns are still fetched and indexed, and claims only prune afterwards.
* **Answer time is set by arrival of data, not by join compute.** The join runs incrementally as tuples arrive;
  an answer appears as soon as its last tuple is in. That tuple comes from discovery (§4.7).
* **B doubles the join's CPU** (4.5 vs 2.2 s in window 1, 5.6 vs 2.3 s after) and raises GC, which explains
  the delayed document-only answers of §4.6.
* **Avoidable overhead, unrelated to composites (15% of CPU, attributed to `@traqula`):** no query is parsed.
  * 2.5–2.8 s: *building* parsers. `ActorDerivedResourceIdentifySparqlEndpoint` identifies every derived
    resource through `mediatorQuerySourceIdentifyHypermedia`, which creates a `QuerySourceSparql`, which
    creates a `SparqlEndpointFetcher`, whose constructor builds a full Traqula/Chevrotain SPARQL grammar
    (16 ms of CPU, measured), used only by `getQueryType`, which `QuerySourceSparql` never calls (a parse
    takes 0.1 ms). About 150 times in 30 s, each blocking the engine just as an endpoint is found.
  * 1.2–1.7 s: the quad-pattern link extractor walked the query's algebra tree (`algebraUtils.visitOperation`)
    for every quad of every document.
  * 0.4 s: generating the SPARQL strings sent (`actor-query-serialize-sparql`); real work.
* **Fixed 2026-11-23** (uncommitted; mounted locally via `scripts/mounts.sh`):
  * `QuerySourceSparql` (comunica fork): one parser shared by all fetchers (`sparqlQueryParser` option).
  * `ActorExtractLinksQuadPatternQuery` (link-traversal fork): the candidate patterns are collected once per
    query operation (`WeakMap`); each quad is matched against that list. Its 11 tests pass.
  * Effect (pattern-only q16, one run, first 30 s): `@traqula` 4.6 → 0.6 s; documents requested 3,099 → 3,743
    (+21%); SPARQL requests 1,278 → 1,525. Arrival in this single run: first 14.4 s, median 19.5 s, last
    27.9 s, within the spread of earlier runs; needs the repeated comparison.
  * Both are generic engine costs, equal in every configuration; they belong upstream (Comunica,
    `fetch-sparql-endpoint`).

**Join share and composites.** A larger join share does not by itself favour composites: what counts is the join
work a composite *removes*. In FedShop the engine's join is mostly cross-pod (product ↔ offer ↔ review), which
no endpoint can take over; composites only take intra-pod star joins. And the leaner the engine, the less it is
CPU-bound, so CPU saved converts less into time; what remains for composites is fewer dependent round trips and
less data (cf. the 80 ms HTTP delay, §2). Bound composites are the one way to push cross-pod joins out, once
their bookkeeping (twice the join CPU) is reduced.

---

## 5. Code changes (all uncommitted)

**`comunica-adaptive-derived-resources`** (branch `feature/query-derived-resources`), package
`actor-rdf-join-inner-multi-stems`:

* `StemsControllerStream.ts`:
  * flags `VIRTUAL_COMPOSITES` (on), `DRAIN_COMPOSITES` (on), `CLAIM_DIRECTED_ROUTING` (only acts with virtual
    off);
  * the timestamp-rule controller filter;
  * bound claims;
  * `valueSelectivity()`.
* `StemsOperatorStream.ts`: virtual-composite attachment, per-part timestamps, `takeTimestamp()`,
  `countTuplesWithValues()`.
* `filters/CompositeClaim.ts` (new): claims per domain and per bound batch, `registrationOf()`.
* `filters/DelegatedPatternsFilter.ts` and `DelegatedPatternsFilterIndex.ts`: `registeredAt`, bound values,
  several filters per domain.
* `test/StemsClaimRouting-test.ts` (new).

Package `actor-query-source-identify-hypermedia-sparql`: `QuerySourceSparql.ts` shares one SPARQL parser across
all fetchers (§4.8).

**`comunica-feature-link-traversal-adaptive-derived-resources`** (branch `feature/improve-union-derived-resources`):

* `actor-derived-resource-execute-composite-source`:
  * the actor: seeds, targets and bound requests (`DERIVED_BOUND_COMPOSITES`, `DERIVED_BOUND_DEBUG`);
  * `lib/BoundCompositeCoordinator.ts` (new);
  * `test/BoundCompositeCoordinator-test.ts` (new).
* `actor-derived-resource-execute-composite-source`, FILTER pushdown (`DERIVED_FILTER_PUSHDOWN=1`, debug
  `DERIVED_FILTER_DEBUG=1`): `lib/FilterPushdown.ts` (new) selects the conjuncts of the query's filters that
  apply to every occurrence of the block's patterns (scope passes through joins, unions, the left side of
  OPTIONAL/MINUS, DISTINCT, REDUCED, ORDER BY, BIND; anything else starts a new scope) and mention only block
  variables, without EXISTS or aggregates; `blockQuery()` wraps the block's BGP in them, for whole and bound
  requests. `test/FilterPushdown-test.ts` (new, 9 tests).
* `actor-derived-resource-partition-star-first`: block extension (`DERIVED_EXTEND_BLOCKS`).
* `actor-extract-links-quad-pattern-query`: candidate patterns cached per query (§4.8).
* `engines/config-query-sparql-link-traversal/.../wrapper-prioritize-derived-resources-and-datasets.json`:
  storage fix.
* `delegation-paper.tex`: the TODO from §4.4.
* The existing placeholder tests of these two actors already failed before these changes.

**`jbr-experiment-fedshop-discovery-enable-proxy-tracking`**: storage-fix override and README entry.

**How the engine is run locally:** the published image, with compiled JS mounted over it
(`scripts/mounts.sh`). The image's own versions of the touched packages were checked to match the sources
except for these changes. Rebuild with `npx tsc` at each repo root.

---

## 6. Tests to run

In rough priority order. Local scripts are in `scripts/` (`up.sh` starts Virtuoso, CSS and the proxy on network
`fedshop-local`; `run_queries.py <label> <image> <q#id>…` runs queries, with `ENGINE_MOUNTS`, `ENGINE_ENV` and
`ENGINE_LOG`). The scripts write `output/` and `proxy-run.json` next to themselves; don't commit those. The
running benchmark still uses the scratchpad copies.

1. ~~**Bound composites vs the rest**~~ Done 2026-11-23 (§4.6). Three rounds are too few for first-result
   times; rerun with more rounds (≥ 10) once the q16 regression is understood.
2. **Solid server with workers**: run on 2026-11-23 but void, since the CSS config ignores `-w` (§4.7). Next: a
   CSS config that keeps the default initialiser sequence (mount it over `css-config.json`), confirm with
   `docker top fedshop-css` that 4 processes run, then rerun `scripts/css-workers.sh`. Also fix the CPU sampler,
   which overwrites the phase markers (it writes with `>` while the markers are appended). The run gave 6 rounds
   of P/V/B on q12 and q16, used in §4.6.
2b. **CPU profile of B on q16** (`--cpu-prof` in the engine container): where the engine time behind B's 13 s
   delay of document-only answers goes.
2c. `run_queries_stream.py` times rows exactly as of 2026-11-23 15:00 (it used to time each row when the next
   one arrived); `analyse_css.py` corrects older files.
3. ~~**VM storage-fix combinations**~~ Done 2026-11-23: no effect on the VM (§4.7).
4. **VM tracking run with the new generator** (`38166e0…`, which logs `headers_ms`). Push
   `jbr-experiment-fedshop-discovery-enable-proxy-tracking`, then `npm ci && npm run jbr -- prepare && npm run jbr -- run`
   on the VM (this regenerates the data). Decomposes document time into server wait and transfer on the VM.
5. **Bound composites, sensitivity:**
   * `SELECTIVITY_THRESHOLD` (0.1 / 0.3 / 0.6) and `MAX_BATCH` (50 / 500);
   * q01, q14 and q06 (in q06 the vendor block is the seed and the product star is bound on its subject, which
     traversal can reach as well);
   * more instances than instance 0.
6. **Skip or deprioritise documents in claimed pods.** Once a pod's composites cover the query's blocks, its
   documents only serve link discovery. Expected to unload the document server; worth measuring once
   item 2 is known.
7. **Profile the engine** (`node --cpu-prof` in the container) on q16: where CPU goes, and the unexplained
   3–5 s window with no requests early in every query.
8. **Reproduce the rare missing rows** (repeat q16 and q01 many times in pattern-only and virtual).
9. **Drain on or off by default** (`DRAIN_COMPOSITES`): mixed so far (q13 first result better without it, q06
   early arrival worse).

---

## 7. Decisions needed

* **Parameterised composites:** is a composite still the same derived resource when it receives `VALUES`
  (the template is the resource, the bindings are a request parameter)? This decides how §4.6 enters the paper.
* **Paper positioning of bound delegation** (sketch): Membership extends with a value test (μ(v) ∈ V); Pruning
  needs anchors ∪ {v} in a pattern, so binding a non-anchor can cost one level of pruning depth, which is where
  the timestamp rule comes in; τ per (domain, batch); the cost proposition with |D_V| instead of |D| and one
  dependent round trip. It answers the "empirical question" left open in *Reducible Decompositions* (scan vs
  bind, decided per pod at run time). Related work: FedX bound joins, brTPF (check the citation).
* **CSS workers as a benchmark change** (§6 item 2).
* **q07 and q08 rating OPTIONALs:** remove or keep (recorded in the README if removed).
* **What to commit**, and whether to keep claim-directed routing (it doesn't pay on FedShop).

---

## 8. Proposals: where the selective part lives, and a micro-benchmark section (2026-11-23, not decided)

*Checked against `delegation-paper.tex` the same day; see "Fit with the paper" at the end of this section.*

**Observation.** In the discovery adaptation of FedShop, the selective constants of the analytical templates
(product type in q01, q03, q04, q14, q16) live in producer pods, while the data joined with them (offers,
reviews) lives in vendor and rating-site pods, connected by `?listing fs:listingOf ?product`. No single
endpoint can apply the constant to the offers or reviews, so a composite there is as unselective as its
patterns (§4.2). Also, **composites carry none of the query's FILTERs**: in V on q16, none of 2,580 SPARQL
requests contains one; the review star is requested as
`SELECT ?review ?page ?rating1 ?site WHERE { ?review bsbm:reviewFor ?page . ?review bsbm:rating1 ?rating1 . ?review dc:publisher ?site . }`
without `FILTER (?rating1 >= 8)`.

Proposals, in order of how little they change the benchmark:

1. **FILTER pushdown into composites (engine only, benchmark unchanged).** Add every FILTER whose variables are
   all bound by the block to the composite's query. A filter on one variable of a star then removes rows of the
   whole star at the endpoint; a pattern-level request can at best filter its own pattern, while the star's
   other patterns still ship everything. This is the composite's structural advantage and is currently unused.
   Applies to q01, q03, q04, q05, q10, q14 and q16 as they are.
2. **Co-located templates (queries added, data unchanged).** Templates whose selective constraint sits in the
   same pod as the join, built from patterns already in the BSBM templates (q10, q15) by anchoring on the vendor
   or reviewer instead of on a product:
   * offers of vendors in country C, `deliveryDays <= 3`, `validTo > D`, with price and the product's label
     (vendor pod: offer ⋈ vendor; pods of vendors in other countries return nothing);
   * ~~reviews by reviewers from country C~~ (reviewers have their own pods, so this crosses pods; see below);
     reviews on rating sites in country C with `rating1 >= 8` qualifies instead.
   The cross-pod product join remains but starts from few rows, which is where bound composites apply.
3. **Data layout (data changed, queries unchanged).** Vendors and rating sites republish `<product> rdf:type <T>`
   (and the label) for the products they list, as shops state a product's category. The existing queries then
   find the type constant in vendor and rating-site pods too, and a composite there is selective (q16: 81 of
   9,986 offers). To check first: whether FedShop's original data gives vendors and rating sites their own copies
   of the product descriptions, which the discovery adaptation replaced by `fs:listingOf`. If so, this restores
   FedShop's layout rather than inventing one. Pattern-only also finds the triple there, so the comparison stays
   fair.
4. Larger scale (more offers and reviews per product) only makes shipped data heavier; weaker on its own.

**Micro-benchmark section: where composites lose.** A small synthetic federation (or the generator's knobs), one
factor at a time, P vs V vs B:

* selectivity of the in-source join or filter, 1% → 100% (at 100% a composite ships as much as its patterns);
* fan-out: multi-valued attributes in a star multiply composite rows (a star with k values per attribute ships
  their product), so a composite can ship more than its patterns;
* request latency and a cap on parallel requests (0 ms and unlimited, as locally: nothing to save; 80 ms as in
  the experiment's delay actor);
* discovery timing: a composite found after its patterns' data has arrived (duplicate work, claim overhead);
* endpoint coverage 25% → 100% (the ablation discussed earlier);
* endpoint cost: heavy composite queries on a slow endpoint delay the first rows compared to patterns;
* bound composites with unselective seeds (the selectivity threshold's job).

Each as a crossover plot; if the engine's own decisions (selectivity estimate, bound vs whole) track the better
side of each crossover, that is itself a result.

**Keeping it honest:** keep the original FedShop results in the paper, labelled as such; justify each change
independently (realism, FedShop's original layout) and record it in the experiment README with date and reason
*before* running; define added queries by a rule (where the selective constraint sits relative to the join: same
source, other source, none) and report every instance, including those where composites lose.

**Fit with the paper (checked 2026-11-23).**

* *FILTER pushdown stays within the BGP story.* For a FILTER `F` with `vars(F) ⊆ vars(B)` at the block's group
  level, `σ_F` commutes with the join and distributes over the disjoint decomposition of B, so the resource
  answers `σ_F(B(A))` and the default plan still prunes on the anchors alone: Membership, Pruning and the
  Characterisation are unchanged, as they never look at F. Base pruning still removes all of `B(A)`, mappings
  failing F included, since F would discard those anyway. In the cost proposition `|D|` becomes `|σ_F(D)|`. One
  remark suffices; the theory stays about conjunctive blocks. Limits: only filters local to the block (not inside
  an OPTIONAL, not mentioning outside variables), and the endpoint must evaluate F as the engine does (datatype
  and regex semantics; cf. q13's integer/decimal duplicate).
* *Republishing `<product> rdf:type <T>` in vendor pods does not fit.* The pattern's anchor is `?product`, which
  lies in the producer's namespace, so by Membership a vendor's resource is never authoritative for a block
  containing it (and Assumption "Scope completeness" fails: the vendor does not hold all triples about the
  product). The block would have to be delegated without pruning, which the paper calls a latency optimisation
  rather than a work reduction, with duplicates to remove. Proposal 3 is withdrawn in that form.
* *What fits instead:* put the selective triple on a subject the vendor hosts, the listing (`vendorN/ProductM#it`
  is in the vendor's namespace): `?listing <category> <T>`. The vendor block
  `{?offer bsbm:product ?listing . ?listing fs:listingOf ?product . ?listing <category> <T> . ?offer bsbm:vendor ?v}`
  has anchors `{?offer, ?listing}`, both bound by `?offer bsbm:product ?listing`, so it is reducible and prunable
  at depth 1; the constant is an object, not an anchor. It needs the template to constrain the listing's
  category ("offers listed under category T"), and the generator to state it on listings and review pages.
* *Co-located templates, checked against the data:* the vendor's country is on `vendorN/Vendor0#it`, in the
  vendor's namespace, so offer ⋈ vendor-country is co-located and reducible (anchors `{?offer, ?vendor}`, both in
  `?offer bsbm:vendor ?vendor`). Reviewers, however, live in their own pods (`reviewerN/profile#it`), so
  "reviews by reviewers from country C" crosses pods and does not qualify; the rating site's own country
  (`ratingsiteN/RatingSite0#it bsbm:country`) would.

**FILTER pushdown implemented (2026-11-23).** See §5. Smoke run, derived q16: 58/58 rows; the 120 review-star
composites carry `FILTER ( ( ?rating1 >= "8"^^xsd:integer ) )` and together return 0.71 MB. Queries it applies
to as they are: q01 (`?value1 > 583`, product star), q06 (regex on `?label`, product star), q13 and q14
(`?product != <…>`, product star), q14 and q16 (`?rating1 >= 8`, review star); q12 has none (control).
Comparison P vs D (derived with pushdown), 6 queries, 4 rounds, both with the CPU fixes: `scripts/compare-filter.sh`,
`scripts/analyse_filter.py`. Exact per-row times, medians of 4 rounds, seconds since the query was sent:

| query | P first / median / last | D first / median / last | consistency over the 4 rounds |
|---|---|---|---|
| q14 | 8.2 / 10.6 / 17.1 | **3.2 / 9.5 / 13.1** | first 2.9–3.4 vs 7.5–9.0; last lower in all 4 pairs; document-only answers too (first 3.4 vs 8.2, last 13.1 vs 17.1) |
| q01 | 3.6 / 6.2 / 13.1 | 3.3 / **4.1 / 12.0** | median 3.5–4.3 vs 4.7–7.0 in all 4; last lower in 3 of 4 |
| q06 | 3.9 / 4.0 / 16.4 | 4.7 / 5.2 / 15.1 | first and median noisy; last lower in all 4 (≈1 s) |
| q13 | 2.0 / 3.6 / 5.0 | 0.8 / 4.5 / 5.0 | first lower in all 4, median higher, last equal |
| q16 | 12.8 / 17.5 / 23.5 | 14.2 / 17.0 / 23.6 | no gain; first later in 3 of 4 |
| q12 (control) | 3.0 | 2.6 | equal |

Rows complete in all 48 runs (q13's 99: §4.4). SPARQL bytes still higher in D (q16 52.7 vs 37.5 MB):
composites come on top of the pattern requests.

*Attribution:* this run has no derived arm without pushdown. In the earlier run (no CPU fixes, §4.6) V already had
q14's early first result (4.1 vs 7.7 s) but not its earlier last result (16.9 vs 16.9 s), nor q01's earlier median.
So pushdown plausibly gives q14's last result and q01's median, not q14's first. A V arm in the same setup settles it.

**Templates and expected effect, checked against the VM full run (fedshop-v1, 17–19 Nov):** q07, q08, q10 and q15
showed no derived benefit there (last result q07 24.8 vs 24.6 s, q08 25.7 vs 26.4 s, q10 3.4 vs 3.5 s, q15 34.8 vs
25.5 s), and pushdown will not change that: q07/q08 rows are released at the end of traversal (OPTIONAL), q10 is
already fast and its constant product leaves little to filter, q15 has no filter. Pushdown helps where a large,
unselective block gets a selective filter: q01, q14 (seen), q16 (pushed but crawl-bound), q04 (needs per-component
filter scope, as both UNION branches share `?product rdfs:label ?label`), q03 (less work, rows only at the end).

**Next candidate: the selective IRI in the vendor's own star.** Listings and review pages carry their product's type
(`<vendorN/ProductM#it> rdf:type <T>`), and templates constrain it. The vendor block then has anchors
`{?offer, ?listing}` in the vendor's namespace, is reducible, and its constant is an object, so the paper's results
apply unchanged; q16's offer composite would return 81 of 9,986 offers and the review composite 540 of 53,637.
Answers from document-only producers stay crawl-bound unless the product IRIs in composite rows are queued as
prioritised links (the composite actor returns `{ links: [] }` now); reachability is unchanged, as the
`fs:listingOf` objects are followed from vendor documents anyway. Needs a generator change and template changes,
recorded in the experiment README before running; a local prototype can patch instance 0's data.


---

## 9. Bound composites (B): where the overhead was (2026-11-23)

**CPU: the selectivity estimate, fixed.** In the q16 profile, B's extra join CPU was almost all
`StemsOperatorStream.countTuplesWithValues` (2.5 s in the first 30 s, 3.0 s after): each new target scanned every
stored tuple of the operator and built a `boundValueKey` string per tuple (240 targets × ~19,000 tuples), which also
drove GC. Now the per-value counts are built once per variable on the first question and updated as tuples are
stored; a question costs one lookup per seed value. SteMs tests: 86 pass. Effect (q16 profile):

| | join CPU, first 30 s / after | GC after 30 s | engine busy after 30 s |
|---|---|---|---|
| B before | 4.5 / 6.0 s | 13.4 s | 47.0 s |
| B after | 3.3 / 2.4 s | 6.0 s | 27.1 s |
| V | 2.2 / 2.5 s | 8.6 s | 33.9 s |

Requests were never the overhead: B sends fewer SPARQL requests than V (q16: 2,420–2,464 vs 2,580); its 376
bound requests carry 145 KB. About 280 of them go to producers and return nothing (every discovered endpoint is
asked every block); cheap, but avoidable.

**Arrival is still late after the fix** (one run: q16 median 26.3 s, last 32.5 s). Two causes, from the proxy log
and per-answer provenance:

1. *Coverage of the bound values.* Seed values come only from seed composites, i.e. from producers with an
   endpoint. Offers and reviews of products from document-only producers, held by the discovered vendors and
   rating sites, therefore come only through the base pattern requests to those pods, which the pattern actor
   defers until the composites have responded (median 38.8 s). Answers with a document-only product and a
   discovered rating site: B 32.1 s, D 16.6 s, P 22.7 s (median). Fix: also feed the coordinator the values of
   the seed region that base operators store (products of type T read from documents), so targets cover them.
2. *Known members are slower in every derived configuration* (not B-specific). The 10 known vendors and 10 known
   rating sites are queried by the federation side at 0–2 s in every configuration; composites only reach the
   discovered ones (found from ~16 s). q16, P vs D over 4 rounds, median of the per-round medians (ranges do not
   overlap):

   | answer's product / review site | n | P | D |
   |---|---|---|---|
   | endpoint / discovered | 21 | 19.0 | **15.8** |
   | endpoint / known | 17 | **14.0** | 19.7 |
   | document-only / discovered | 13 | 22.6 | **16.9** |
   | document-only / known | 7 | **14.7** | 23.5 |

   Composites help where they apply, and the known-member path loses 5–9 s, which cancels the gain on q16. In
   q14 the known path is equal (P 9.6 vs D 10.0) and endpoint/discovered gains (10.5 → 3.4 s). Hypothesis to
   test: `DRAIN_COMPOSITES` (the eddy reads a composite until it has nothing ready) starves the base operators
   that carry the known members' data, when composites are large (q16's rating-site composites). It is a static
   flag; an environment override makes it testable.

### 9.1 Follow-up (2026-11-23 evening): drain switch, base-value seeds, where the slow answers wait

Engine changes (uncommitted): `STEMS_DRAIN_COMPOSITES=0` turns draining off (`StemsControllerStream`);
`DERIVED_BOUND_BASE_SEEDS=1` also feeds the coordinator the values that base operators holding a constant store
(`StemsControllerStream.onBaseTuples`, `StemsOperatorStream.storedListeners`/`forEachStoredTuple`,
`BoundCompositeCoordinator.tapBase`; one new unit test). Runs: `scripts/compare-drain.sh`, analysis
`scripts/analyse_drain.py`. **Only round 1 is clean**: from round 2 four QLever containers ran at 100% CPU on the
same machine. Round 1, median row time (s):

| q16 | first | median | last | answers with a known review site |
|---|---|---|---|---|
| pattern-only | 12.4 | 17.3 | 24.6 | 13.6–14.0 |
| derived full, drained | 13.1 | 16.1 | 22.2 | 19.8–22.2 |
| derived full, not drained | 13.9 | 17.0 | 22.3 | 20.9–22.3 |
| bound + base values, drained | 17.4 | 18.6 | 34.8 | 32.0–34.7 |
| bound + base values, not drained | 17.3 | 18.9 | 37.3 | 34.8–37.3 |

- **Draining is not the cause** of the slow known-site answers (no change with it off; q14 also unchanged).
- **Base-value seeds make bound composites worse.** Document values trickle in, so the 240 targets each send many
  small requests (≈2,070 bound requests instead of 376) and the single engine core falls further behind. Dropped.
- **Not the shared Virtuoso.** Latency of the discovered members' endpoints (main Virtuoso) with composites:
  p50 ≈20 ms vs ≈12 ms, p90 ≈80 vs ≈55 ms, max < 1 s; known members (separate Virtuoso) unchanged.
- **Not the offer.** Regrouping by the offer's vendor as well (`scripts/analyse_offer.py`, looked up in the
  generated data): answers whose offer *and* review come from known members (n=15, no discovered member involved)
  are 13.9 s pattern-only vs 19.7 s derived full (4 filter-run rounds).
- **Not the fetch order.** The product's data is fetched equally early in both (endpoint producers: first SPARQL
  request ≈3 s; product documents ≈12 s; `scripts/analyse_product_fetch.py`). Yet answers come at 14–20 s: the
  data waits *in the engine*.
- **Most likely: engine CPU (one core).** In the first 20 s the engine receives 74 MB (pattern-only) vs 83 MB
  (derived full), and sends 2,580 vs 1,980 SPARQL requests over the run; it is at 93–98% of its core. Extra
  composite work delays everything queued behind it, including answers that need no composite. Test: rerun with
  the engine at 2 and 4 cores; if the known-site gap closes, the benefit of composites is capped here by engine
  CPU, not by the idea.

### 9.2 Where the engine's CPU goes before the known members' answers (2026-11-23 night, machine idle)

Correction to 9.1: more cores is not a test, the engine's JavaScript runs on one thread.

- **CPU profile, q16, 3 rounds each** (`scripts/profile-q16.sh`, `profile_windows.py`, `analyse_windows.py`;
  samples binned by time since the query was sent, `hook.js` stamps each profile with wall time). The engine is
  at 100% from the start in both configurations, and up to 15 s both do the **same work**: 14.84 s CPU
  pattern-only vs 14.91 s derived full, every kind of work (GC, document parsing, store, join, SPARQL, link
  extraction, composite actors) within 0.5 s. Yet the answers whose offer and review both come from known
  members (n=15, no discovered member involved) arrive at ~15 s pattern-only vs 23–26 s derived full. So the
  delay is not extra CPU; the same work is done in a different order, or results are held.
- **Drain rerun** (rounds 2–3 clean): known/known median, drained 19.8 / 20.3 / 23.0 s; not drained
  20.9 / 16.7 / 15.3 s; pattern-only 13.4–13.8 s.
- **All clean q16 rounds of derived full, drained, without timeline logging: 10/10 slow** (known/known 19.3–25.9
  s). Two rounds with `STEMS_TIMESERIES_LOG=1` (new switch: the SteMs timeline written to stderr at the end) were
  fast (13.9, 15.1 s; last row 16.4, 18.4 s vs ~22 s pattern-only). Timeline logging does not change routing; it
  only adds work at each routing update, which could break up long synchronous eddy passes (drained composites)
  and let the event loop run. Being tested: alternating with/without logging, 3 rounds each.
- **Result (alternating, 3 rounds each): logging makes no difference.** Derived full known/known 15.0 / 21.8 /
  17.0 s without, 18.3 / 21.4 / 17.4 s with; derived full simply varies a lot (13.9–25.9 s over all clean rounds),
  pattern-only does not (12.5–16.6 s).
- **What the delay follows: the `fs:listingOf` tuples.** SteMs timelines (`scripts/analyse_timeseries.py`): the
  product side is *not* late (the producers' product-star composites deliver all 115 tuples at 3.4–3.9 s). The
  time by which half of the base `?listing fs:listingOf ?product` tuples are read tracks the known/known answers:
  pattern-only 18.0 s → 13.0 s; derived rounds 18.4 → 13.9, 22.0 → 18.3, 27.4 → 21.4 s. Derived full also has
  **one-pattern composites** for `?listing fs:listingOf ?product` and `?page fs:listingOf ?product` (5 composite
  operators in all, fed by 120 pods): 28,500 tuples, of which ~24,000 (85%) are pruned as already covered. The eddy
  reads composites first, so this work goes ahead of the base listing tuples from the known members. A one-pattern
  block offloads no join (it is the request a pattern-level resource makes anyway); new switch
  `DERIVED_SKIP_SINGLE_BLOCKS=1` (in `bus-derived-resource-execute` `compositeBlocks`, so the composite and
  triple-pattern actors agree) leaves such blocks out. Test: `scripts/compare-single.sh`.
- **Result (3 rounds, alternating; all rows correct).** q16: one-pattern composites removed → first / median /
  last 12.9 / 15.7 / 18.3 s (derived full 13.4 / 16.1 / 21.7; pattern-only 12.1 / 17.9 / 24.5); known/known
  answers 14.2–14.7 s (derived full 16.1–21.2, pattern-only 13.1–13.9). q14: first row 5.0 s (was 3.4; pattern-only
  8.6), last 13.4 s (12.2; 16.2): the `?page fs:listingOf ?product` composite had been read early as its own
  operator; now those tuples sit in the ~46k-tuple base listingOf stream. Per pod, derived full fetched
  `fs:listingOf` three times (the deferred pattern request plus two one-pattern composites for `?listing` and
  `?page`): +240 requests, +13 MB on q16. **Now unconditional** (no switch): `compositeBlocks` in
  `bus-derived-resource-execute` leaves out blocks of one operation.
- **Why the same triples also come from documents.** Every document of a pod with an endpoint is fetched *before*
  the engine's first SPARQL request to it (none after: the dynamic link filter works once set). Rating sites,
  derived full q16: 139 before the pod root is requested, **1,317 while the 1 MB root downloads**, 74 after; vendors
  50 / 195 / 16; producers 526 / 77 / 14 (the `producerN/ProducerN` documents, linked from `bsbm:producer`).
  Holding (`holdPodLinks`, on in both images) only starts once the root's description has been read and
  `void:sparqlEndpoint` found; the links into the pod already queued are crawled in parallel with the root.
  Possible fix (not done): hold a pod's links from the first link into it until its root is read.
  *Where those links come from:* the producers' product documents carry back-links to the rating-site pages
  about the product (`<ratingsite18/Product7195#it> fs:listingOf <producer103/products/2001-02#Product7195>`), which
  link extraction follows as matching `?page fs:listingOf ?product`. By the time a rating site is reached, ~130 links
  into it are queued (ratingsite18: 128); the first is popped at 13.58 s, the root at 13.95 s, all 128 pages within
  1.4 s with up to 63 requests in flight. The same triple thus reaches the engine three ways: the producer's
  document, the rating site's endpoint, and the rating site's page.

### 9.3 Lowering links into a pod whose dataset document is pending (2026-11-23 night, not yet compared)

Implemented (uncommitted): `LinkQueueDerivedResourcePrioritization` lowers, from the first `void:inDataset <D/>` (or
`pim:storage`) link, every link into D to priority -1 until D's document has been handled
(`IDynamicFilter.datasetHandled`, signalled by `ActorExtractLinksSolidDerivedResources` once D's derived resources,
if any, have run), then restores each link's priority and queue place (`setPriority`); 10 s timeout. Lowered, not
held: with nothing else queued they are still crawled. Links already queued are found through an index of pushed
urls by container (a full queue scan cost 1.2 s CPU per q16 run: 421 datasets × ~9,300 queued links; the index
0.21 s). Smoke test q16 derived full: documents from pods with an endpoint 2,745 (23.4 MB) → 745 (14.5 MB), total
requests ~16,900 → 14,242, 58/58 rows. The ~745 left are requested before any page of their pod has come back (mostly
`producerN/ProducerN`). Comparison script `scripts/compare-lower.sh` (pattern-only / derived full × on/off,
`LINK_LOWER_PENDING_DATASETS=0` is the off arm), analysis `analyse_lower.py`. Local run directory backed up to
`~/projects/data-analysis/local-run-2026-11-23/` (the scratchpad in /tmp is cleared at boot).

**Result (2026-11-24, `compare-lower.sh`, 3 rounds alternating, machine idle, all rows correct).** Medians, s:

| | q16 first / median / last | q16 known/known | q14 first / median / last | requests (q16) | endpoint-pod pages (q16) | lowering CPU |
|---|---|---|---|---|---|---|
| pattern-only | 11.9 / 17.3 / 24.7 | 13.1 | 8.1 / 9.9 / 15.5 | 15,572 | 2,435 (23.3 MB) | – |
| pattern-only, lowering | 12.4 / 19.5 / 25.0 | 13.6 | 8.5 / 11.2 / 17.7 | 13,914 | 777 (15.5 MB) | 132 ms |
| derived full | 12.8 / 15.2 / 17.0 | 14.0 | 4.5 / 9.6 / 12.4 | 16,464 | 2,967 (24.4 MB) | – |
| derived full, lowering | 13.1 / 16.8 / 22.0 | 17.1 | 4.4 / 9.1 / 13.8 | 14,238 | 741 (15.1 MB) | 149 ms |

Lowering works mechanically (about 2,000 fewer requests, ~9 MB fewer duplicate pages, own CPU 0.12–0.17 s per
query) and the query *completes* 5–8 s sooner (q16 derived 56 s vs 60–67 s; q14 50–52 vs 56–60 s), but **results do
not arrive sooner**; q16 derived's last row was later in 2 of 3 rounds (22.0 / 22.6 vs 17.0 / 16.8 s). Reason: the
link queue is saturated, so freed slots are refilled at once with other documents; data received per 5 s window
in the critical 15–25 s stays the same (20–25 s: 14.6 vs 15.0 MB), only its mix changes. Not a timeout artefact:
pages of pods without an endpoint follow their root as soon with lowering as without (median 1.6–3.0 s).

**Decision 2026-11-24:** link lowering removed again (all seven files restored from git). FILTER pushdown is now
unconditional in `ActorDerivedResourceExecuteCompositeSource.blockQuery` (no `DERIVED_FILTER_PUSHDOWN` switch).
Next: VM rerun of instance 0 of every template, pattern-only vs derived full, endpoints at 100%, in a copy of the
real experiment, with an image rebuilt from the current forks.

## 10. VM rerun: instance 0 of every template, pattern-only vs derived full (2026-11-24/25)

**Setup.** VM copy `~/jbr-experiment-fedshop-discovery-instance0` (driver `run-all.sh`, copy in
`scripts/vm-instance0-run-all.sh`). Engine image `:dev` sha256:5841d954… (FILTER pushdown unconditional, one-pattern
composites dropped, no link lowering), generator `:dev` sha256:b51b7114… (to be pinned after the evaluation),
`services: {select: largest, brands: 1.0, shops: 1, review_sites: 1, seed: 42}`, i.e. every service at 100 %.
One warm-up plus 6 replications per template; combination_0 = derived full, combination_1 = pattern-only (run one
after the other, 23:28–01:32 and 01:32–03:29). Results copied to `data-instance0-2026-11-25/`; table from
`scripts/analyse_instance0.py data-instance0-2026-11-25`.

**Correctness.** No errors. Recall 1.00 in every replication except one derived-full q04 run (19/20 rows, 57 failed
requests in that run). Pattern-only q13 returns 100 rows of which 99 are correct (one duplicate) in all 6 runs;
derived full returns exactly 99.

**Result arrival (medians of 6, s; ratio < 1 means derived full is faster).**

| template | first: full / pattern | median row: full / pattern | last: full / pattern | requests: full / pattern |
|---|---|---|---|---|
| q01 | 7.3 / 8.3 (0.87) | 9.9 / 13.6 (0.73) | 16.0 / 16.5 (0.97) | 13,362 / 13,530 |
| q03 | 8.8 / 11.2 (0.78) | 10.1 / 19.2 (0.53) | **17.3 / 38.3 (0.45)** | 15,180 / 12,958 |
| q04 | 13.3 / 14.2 (0.93) | 19.9 / 22.0 (0.90) | **23.7 / 63.5 (0.37)** | 14,556 / 9,891 |
| q06 | 16.8 / 19.9 (0.84) | 17.6 / 23.7 (0.74) | **24.0 / 39.9 (0.60)** | 13,746 / 12,612 |
| q12 | 12.0 / 14.8 (0.81) | (1 row) | | 15,512 / 12,339 |
| q13 | 4.0 / 6.0 (0.67) | 11.7 / 10.9 (1.08) | 12.5 / 11.8 (1.06) | 12,807 / 10,224 |
| q14 | 12.5 / 17.3 (0.72) | 45.6 / 43.8 (1.04) | 54.5 / 51.1 (1.07) | 10,264 / 8,375 |
| q16 | 33.5 / 31.6 (1.06) | 65.9 / 64.6 (1.02) | 71.6 / 76.8 (0.93) | 11,850 / 9,626 |
| q02, q05, q07–q11, q15 | within ±15 %, mostly < 1 s apart | | | equal |

- Clear gains where the answer depends on the discovered pods: last row 2–2.7× sooner on q03, q04 and q06; first row
  13–33 % sooner on q01, q03, q06, q12, q13 and q14.
- q13, q14 and q16 are a draw after the first row. First-row times on these vary a lot between replications
  (q14 8–32 s, q16 15–61 s, both configurations), so 6 runs do not separate them.
- Templates that only use the known members or few documents (q02, q05, q07–q11, q15) are unchanged, as expected.
- **Derived full makes more requests:** 840–1,680 more SPARQL requests (the composite queries) on the traversal-heavy
  templates, and on q03, q04, q12, q13, q14 and q16 also 1,000–3,100 more document requests. It also traverses
  longer before the query ends (total time q04 106 vs 82 s, q12 114 vs 87 s). Results arrive earlier, but the extra
  traversal is not yet explained. Open question: which documents are these extra ones (links found in composite
  results?).

### 10.1 Where derived full's extra documents come from (2026-11-25)

**Not from composite results.** The composite source returns no links (`ActorDerivedResourceExecuteCompositeSource`
ends with `{ links: [] }`), so its answers cannot lead traversal anywhere.

**On the VM** (`proxy-stats.jsonl`, per publisher, mean per run): the extra documents are pages of rating sites
and vendors that *have* an endpoint (each also gets its 18 SPARQL requests). q04: rating-site pages 4,154 vs
1,390, vendor pages 518 vs 260, producer pages 1,562 vs 1,364. q12, q03 and q16 show the same pattern, smaller.

**Mechanism** (local request log of 2026-11-24, runs `LP-*-off-*` = the current engine, q16 and q14, 3 rounds each;
older local data, but the same effect: +940 endpoint-pod pages per q16 run):

* Nearly all of these pages are fetched *before* the pod's first SPARQL request (after it: 1–10 per run), so
  the link filter works once it is set. They are `ratingsiteN/ProductM` pages, reached through the back-links
  in producer documents (§9.3).
* They are fetched while the pod's root (the container listing that names the endpoint) is loading. Once it
  arrives, the first SPARQL request follows in 0.13 s in both configurations. The pod is only held, and its pages
  filtered, after the root is processed.

| q16, rating-site pods, median | pattern-only | derived full |
|---|---|---|
| root response time | 0.93 s | 1.35 s |
| pages of the pod fetched while the root loads (per pod / per run) | 75 / 1,089 | 175 / 2,119 |
| root arrived → first SPARQL request | 0.13 s | 0.13 s |
| document response time, all pods | 119 ms | 154 ms |
| requests in flight at the proxy (median, documents) | 32 | 43 |

* The Solid server is one saturated Node process (≈1.1 of 32 cores on the VM throughout both runs; `-w` is
  ignored, §4.7). Its throughput is about the same in both configurations (in flight ÷ latency: 43 / 0.154 s ≈
  32 / 0.119 s ≈ 270 per s), but derived full keeps more requests open, so each one, the large root listing
  included, waits longer. Meanwhile more of the pod's pages leak through. Why derived full keeps more requests
  open is not settled (the counter covers all proxy requests; slow composite requests to Virtuoso may be part of it).
* **Cost:** requests only, not result time. §9.3 removed most of these pages (about 2,000 fewer requests on q16)
  without any earlier results, because the saturated queue fills the freed slots at once.

**Options, none tried:** (1) a smaller document naming the endpoint (e.g. the pod's `.meta` or a VoID document)
instead of the large container listing — a benchmark change; (2) Solid server workers, so the root does not
queue behind pages — a benchmark change, needs the CSS config fix of §4.7; (3) a VM run with
`proxyRequestLog: true` on q03/q04/q12/q16 to confirm the mechanism on the 100 % data.

### 10.2 The extra q13 row in pattern-only (2026-11-25)

Pattern-only returns 100 rows on q13 (`SELECT DISTINCT`) in every run, against 99 in the reference; derived full
returns 99. Reproduced on the VM with the instance-0 data served by hand (`scripts/vm-up.sh`,
`scripts/vm-run_queries_stream.py`; pattern-only 3 of 3 runs, derived full 1 run; rows in
`data-instance0-2026-11-25/q13-duplicate/`). The two rows:

```
vendor17/Product1455#Offer400  "Anglicize"  producer12/…#Product1455  "4587"^^xsd:decimal
vendor17/Product1455#Offer400  "Anglicize"  producer12/…#Product1455  "4587"^^xsd:integer
```

* They are different RDF terms, so DISTINCT is right to keep both. The runner compares values only (no datatype,
  numbers normalised), so it sees a duplicate.
* The data has `"4587"^^xsd:decimal`, in the document and in Virtuoso (SELECT as JSON and CONSTRUCT as N-Triples
  both return `xsd:decimal`). **Virtuoso's Turtle writes it as the bare token `4587`**, which Turtle reads as an
  `xsd:integer`. The engine fetches every CONSTRUCT as `text/turtle` (`fetch-sparql-endpoint`
  `fetchTriples`, used by `QuerySourceSparql`), so every decimal with an integral value that comes from a
  pattern request is typed as an integer.
* Pattern-only gets the price twice: as an integer from the vendor17 endpoint's pattern request, and as a decimal
  from the page `vendor17/Product1455`. That page is fetched 0.7–3 s before vendor17's first SPARQL request,
  i.e. in the window of §10.1. Derived full answers this part through the composite (SELECT, JSON, decimal) and
  leaves the pattern request's quads out of the store (`claimedByAcceptedComposite`), so only the decimal
  remains.
* Effect elsewhere: the reference has one integral price in q13 (this one). Values stay numerically equal, so
  FILTERs and the runner's scoring are unaffected; only joins or DISTINCT over such literals across sources can
  differ. Both configurations are exposed wherever pattern requests answer a pattern.

**Fix (2026-11-25, adaptive fork, engine bug fix):** `QuerySourceSparql` now uses `SparqlEndpointFetcherNTriples`
(new file in `actor-query-source-identify-hypermedia-sparql/lib`), which fetches CONSTRUCT/DESCRIBE results with
`Accept: application/n-triples,text/turtle;q=0.9` and parses them with n3 (`n3` added to the package's
dependencies). Unit test added, package tests 99/99. Checked on the VM by mounting the compiled files into the
existing images: pattern-only q13 99 rows in 2 of 2 runs, the price as `xsd:decimal`; derived full 99 rows. Needs
an image rebuild to be in the next run.

### 10.3 Where composites could still gain (2026-11-25, from the derived-full `adaptiveStats` of the VM run)

Tuples that reach the join (sum over operators, first run of each template), derived full / pattern-only:
q16 215,598 / 297,174; q13 109,736 / 136,518; q12 89,212 / 137,011; q08 170,662 / 202,776. The engine is
CPU-bound, so these volumes are what it spends its time on. What is left in derived full
(`data-instance0-2026-11-25/queries/composite-summary-derived-full.txt`):

1. **`fs:listingOf` is never in a composite.** It arrives unbound, 46,105 tuples per occurrence, in every template
   that has it (q01, q03, q04, q06, q07, q08, q10, q12, q13, q14, q15, q16; twice in q16). The chain proposer does
   offer `?offer product ?listing . ?listing listingOf ?product`, but star-first ranks multi-pattern stars first:
   the offer star takes `?offer product ?listing`, the chain is left with one pattern, and a remainder below two
   patterns is dropped. So the hop offer → listing → product (vendor pod) and review → page → product (rating-site
   pod) stays a single pattern, although both ends sit in the same pod, and even the same document.
   `DERIVED_EXTEND_BLOCKS=1` (off) adds exactly this hop to the star; tested as "virtual + extended" on 2026-11-23
   (§4.6) without gain, but under the old conditions (one-pattern composites, no FILTER pushdown, ~25 % endpoints,
   before the CPU fixes), so worth rerunning. A path composite including the hop would replace these tuples, and with a constant product
   (q07, q08, q10, q15) it would return only that product's reviews/offers (now 3,400–6,800 per pod).
2. **The known members are asked one pattern at a time in every configuration.** They are query sources, and
   `claimResources` does not take them up as derived resources. Their unbound pattern answers are most of the
   remaining `reviewFor`, `rating1`, `publisher`, `title` … tuples (e.g. q08: 27,763 per review pattern, of which
   only ~700 are dropped by composite claims). Sending them the same composites would cut most of the remaining
   volume, and it is the known-member answers that wait on the engine's CPU (§9.2). Open question: does this still
   count as the derived-resource contribution, or as FedX-style exclusive groups?
3. **Unbound composites where a binding is known.** q13: `C[?product producer ?producer . ?product label]` returns
   29,999 tuples, while `?producer` has one value from the first pattern. q12: `C[?product label . ?product producer]`
   returns 30,000 for one product. q05: its FILTER depends on the given product's values, so it cannot be pushed.
   The bound composites (`DERIVED_BOUND_COMPOSITES`, off) target exactly this; last time their overhead came from
   base seeds (§9.1), and this case would need only the bind join.
4. **Composites that cannot match**, 420 requests each for nothing: q04 `C[?listing listingOf ?product . ?product
   producer ?brand]` (listing in a vendor pod, producer in a producer pod), q06 offers of the constant vendor7
   (a known member), q07 and q15 offer and reviewer composites. They cost requests, not results. Pruning them needs
   per-pod knowledge (e.g. VoID property partitions).
5. **q04's UNION** keeps `?product producer ?brand` outside both branch composites, so 30,000 producer tuples
   arrive. Distributing it into each branch's composite would avoid that.

**Will not improve through composites:** q02, q09, q10, q11 (lookups answered in 0.7–2 s); q07 and q08 (their
rows are released only when traversal ends: the OPTIONALs and the reviewers' names from reviewer storage, so last
result = query end, ~40–46 s); q15's last row (reviewer country from reviewer storage, document-only).
**Could improve, but do not yet:** q12, q13, q14, q16 (items 1–3), q05 (item 3), and q01/q03/q04/q06 further
(items 1, 2, 5).

### 10.4 Star + chain, extended blocks and constant-first, against the paper's semantics (2026-11-25)

Paper (`papers/federation-of-heterogeneous-data-interfaces`, claims / query_delegation / namespace_claims /
adaptive_planning): any $B'$ can be delegated; the answer is $\Phi_c$(composite answer) $\cup$
$\overline{\Phi}_c$(base answer), with $\Phi_c$ keeping solutions whose every subject lies in $c$'s namespace.
A star is claim-uniform, so the base plan needs none of $c$'s claimed triples for it; a chain or tree is not, so the
base still needs them for mixed solutions (paper TODO (4): "saves join work, not fetches").

* **Star and chain as two composites:** allowed by the routing model (overlapping composites are mutually exclusive
  via the masks), but no solution uses both, so offer ⋈ listing is never delegated as a whole; it only doubles the
  requests. The implementation partitions disjointly anyway.
* **Star ∪ hop as one composite = extended blocks** (`DERIVED_EXTEND_BLOCKS`). Sound: the hub variable is added to
  the anchors, so $\Phi_c$ checks both subjects. But the store-level drop (`claimedByAcceptedComposite`) only drops a
  quad if the pattern contains *all* anchors of the block. `?offer price ?price` and `?offer vendor ?vendor` lack
  `?listing`, so extending the star *loses* their drop; only `?offer product ?listing` quads with both ends in the
  pod are still dropped, and `fs:listingOf` is still taken in whole. This is what the semantics require (mixed
  solutions), so it is not a bug; it explains why "virtual + extended" did not gain on 2026-11-23.
* **Constant-first ranking** (a candidate holding a query constant before stars) makes the composite selective
  (q07, q08, q10, q15: `?page listingOf :P . ?review reviewFor ?page …` returns that product's reviews only).
  Correct like any $B'$, but the block is a tree, so the same base-side cost remains unless the base gets the
  claimed triples differently.
* **Where `fs:listingOf` comes from** (generated data, instance-0 copy): 60,368 triples; 30,184 local (22,150 in
  rating-site pods, 8,034 in vendor pods) and 30,184 back-link copies in producer pods whose subjects are in
  rating-site / vendor namespaces. Under claim semantics a copy is not admitted from the producer pod once the
  claimant (the rating site's / vendor's composite) is known (non-local, Remark "resolving claim status").

Levers that do reduce base-side volume, both following the paper:
1. **Drop non-local claimed copies at ingest** once the subject's claimant composite is known (half of all
   `fs:listingOf`). Non-monotone before the claimant is found (Prop. "claims break monotonicity").
2. **Complement requests for non-uniform blocks:** the base asks $c$ only for claimed triples that can be part of a
   mixed solution, e.g. bound on values from unclaimed partial results, or with a namespace FILTER on the
   non-anchor variable. In FedShop these are nearly empty, which would replace the unbound pattern requests for
   the block's patterns at that pod.

### 10.5 Committed state and the within-pod chain revisited (2026-11-25)

**Committed** (no co-author lines, `--no-verify`: the adaptive fork's hook lints the whole repo, which already
fails on untouched files):
* adaptive fork (`feature/query-derived-resources`): c83478bc6a shared SPARQL parser, f5198c6121 N-Triples for
  CONSTRUCT, 26b3a9bac1 SteMs virtual composites / claim-directed routing / bound-composite hooks, 92a98de7f8 `Set`
  in the components generator config.
* link-traversal fork (`feature/improve-union-derived-resources`): 7c670b3 no one-pattern composite blocks,
  359ad06 link-extraction patterns once per query, fd419e5 FILTER pushdown + bound composites, 122270e extended
  blocks, 1e2572c pim:storage priority, 1906b41 config-query-sparql override. `delegation-paper.tex` left as is.
* lerna-docker (`feature/additional-path-to-publish`): e46b40d host registry address (the user's earlier
  change), b26cc3e local-only serving of published packages, generated config ignored.

**Correction to §10.4/10.5 reasoning (user, 2026-11-25):** with the reachability criterion every `fs:listingOf`
triple is still fetched, parsed and link-extracted, but triples covered by a within-pod chain composite need not
be *indexed*: drop them after link extraction (as the star drop does). This saves store indexing (~9 % of CPU in
the 2026-11-23 profile) and memory/GC (~17 %), not only the join (~9 %). Soundness for K3 (a foreign offer
pointing at a listing in the pod): fetch that listing's triple on demand with a bound request to the pod (or
keep the dropped triples in a cheap side map keyed by listing). Parsing stays.

**Bound composites, why they did not help on 2026-11-23** (§4.6, §9, §9.1): (a) CPU of the selectivity estimate
(fixed in §9); (b) coverage: seed values came only from producer composites while ~3/4 of producers had no
endpoint, so most offers/reviews still came late through deferred base requests (base-value seeds made it worse);
(c) one dependent round trip per pod (seed answer before target request); (d) bound blocks are not accepted for the
store-level drop. With every producer serving an endpoint, (b) largely disappears; (a) is fixed; (c), (d) remain.
q12/q13 are the clearest targets: their unbound composites return ~30,000 rows for 1 and ~100 needed.

### 10.6 Bound-composite policy, the star / star + hop split, and the full run (2026-11-25)

**Bound-composite experiment** (`scripts/vm-bound-experiment.sh`, analysis `scripts/analyse_bound_policy.py`, data
`data-instance0-2026-11-25/bound-experiment/`): q12, q13, q14, q16, 3 rounds, configuration order rotated. Median
over rounds, seconds; every run gave the expected distinct rows.

| query | | derived full | + extended blocks | bound, every seed | bound, one-shot seeds only |
|---|---|---|---|---|---|
| q12 | first | 25.6 | 26.2 | 16.2 | 15.6 |
| q13 | first / median | 3.0 / 14.1 | 2.1 / 15.0 | 2.0 / 14.8 | 2.0 / 14.5 |
| q14 | first / median | 26.4 / 56.0 | 10.3 / 11.2 | 8.7 / 15.0 | 8.3 / 10.2 |
| q16 | first / median | 48.4 / 68.5 | 10.0 / 30.1 | 22.5 / 30.3 | 11.9 / 21.7 |
| q16 | end of query | 94.9 | 91.2 | 119.9 | 89.2 |

* Binding loses only where seeds trickle (q16: 1,512 requests where whole composites need 840).
* A quiet spell in a trickling seed does not mean it is done: after 5 s without new values, q16 `?product` knew
  11 of 219 values and q14 `?product` 5 of 356. So an arrival-rate rule would bind exactly the losing cases.
* The selectivity check never triggered (0 of 3,780 targets requested whole; all were refused for trickling).

**Rule adopted** (link-traversal fork 94b9789):
* A constant subject (one-shot) seed is bound when the values known at the time fit in one request (500).
* A constant object (trickling) seed is always sent whole.
* The selectivity check, the 5,000-value cap and `DERIVED_BOUND_POLICY` are removed.

**Extended blocks keep the star's store drop** (ce1376f):
* An extended block requested whole is taken on as two composite sources over the pod:
  * the star + hop, holding the star rows whose hops are within the pod;
  * the star, holding every other star row, with its claim and store drop.
* One `star OPTIONAL { hop BIND(true AS ?marker) }` request when the resource accepts it, two BGP requests otherwise.
* A bound extended target is still sent on its own.

**This needed an engine fix** (adaptive fork fb70fb3190). The exactness test only placed overlapping composites on
different pods. With a star and its extension on one pod:
* the full star gave duplicates (star ⋈ base hop);
* the split star lost answers, because the star's claim filter also dropped the star + hop rows.

Claim filters now pass a tuple whose block came entirely from composites. The nested case was added to
`StemsClaimRouting-test.ts`: it fails without the fix and passes with it (6,000 seeds, all modes). It holds for
forward hops only, which is all extended blocks make. Backward ones lose answers, and bound extensions are not split.

**SolidBench:** its derived resources are parameterized templates: they answer only their own BGP and take no
join bindings. So extended blocks never form there, and no bound targets arise; both changes are no-ops.

**Smoke run** (`scripts/vm-optional-smoke.sh`, data `data-instance0-2026-11-25/optional-smoke/`, one round):
* All queries returned the expected distinct rows, with no engine errors.
* The star part of every split is empty on FedShop: every star row's hop is in its pod.
* The `OPTIONAL` requests take as long as the extended block's BGP did in q13 and q16 (1.0 vs 0.9 s; 1.2 vs
  1.1–1.3 s median).
* q14 was slow in the extended-blocks configuration, but its plain two-pattern requests were slow too (4.9 vs
  0.8 s), so Virtuoso was under load.
* With bound composites: q12 15.7, q13 3.0 / 15.6, q14 8.4 / 10.7, q16 18.4 / 27.0 (first / median).

**Full run started** (2026-11-25 14:19, `scripts/vm-instance0-run-2026-11-25.sh` on the VM in
`~/jbr-experiment-fedshop-discovery-instance0`, previous outputs in `previous-run-2026-11-24/` there):
* combination 0: derived full;
* combination 1: pattern-only;
* combination 2: derived full + extended blocks + bound composites.

All three run the same mounted code: the N-Triples fix, fb70fb3190, and the actors of ce1376f, via `additionalBinds`.
Combination 2 sets `DERIVED_EXTEND_BLOCKS=1` and `DERIVED_BOUND_COMPOSITES=1` in its own Dockerfile. Derived full and
pattern-only are rerun because the 2026-11-24 results predate the N-Triples and claim-filter fixes. No new image:
for the paper's final runs, rebuild the engine image from the commits instead of mounting.

### 10.7 Full run of 2026-11-25: pattern-only, derived full, derived full + extended blocks + bound composites

Data `data-instance0-2026-11-25/full-run-2026-11-25/`, analysis `scripts/analyse_full_run.py`. Instance 0 of the 16
templates, 6 replications (+1 warm-up), all three configurations on the same mounted code (§10.6). Ratios against
pattern-only, medians over replications (< 1 is faster):

| template | derived full: first / median / last | + extended + bound: first / median / last |
|---|---|---|
| q01 | 0.94 / 0.78 / 0.87 | 0.98 / 0.73 / 0.80 |
| q03 | 0.97 / 0.54 / 0.48 | 0.92 / 0.52 / 0.31 |
| q04 | 0.96 / 0.95 / 0.41 | 0.95 / 1.01 / 0.44 |
| q06 | 0.34 / 0.36 / 0.49 | 0.37 / 0.40 / 0.53 |
| q12 | 0.71 (1 row) | 0.57 (1 row) |
| q13 | 0.79 / 1.12 / 1.06 | 0.61 / 1.23 / 1.19 |
| q14 | 0.42 / 0.92 / 0.95 | 0.30 / 0.21 / 1.07 |
| q15 | 1.03 / 1.02 / 1.05 | 1.28 / 1.14 / 1.17 |
| q16 | 0.48 / 0.98 / 0.95 | 0.34 / 0.39 / 1.10 |
| q02, q05, q07–q11 | 0.85–1.09 | 0.81–1.04 |

**Findings:**
* Extended blocks + bound composites add most on q14 (median 47 → 10 s), q16 (median 68 → 26 s), q12 and q03
  (last answer 42 → 13 s).
* The last answer of q14 and q16 is 7–10% later than with pattern-only.
* q13's median and last answers are 19–23% later.
* q15 got slower, with more variance: first answer 4.6–8.1 s against 4.6–5.7 s for pattern-only. To look into.
* Requests: derived full +13–46% over pattern-only. Extended + bound sends fewer than derived full on q12, q13, q14.

**Correctness:** every configuration's median recall is 1.00. Three runs missed answers:
* **pattern-only q13:** 1 of 6 runs stopped at 53 of 99 rows (last answer 5.9 s, query end 93 s), with no request
  errors. Not yet explained.
* **q04, both derived configurations:** 1 of 6 runs each gave 19 of 20 rows. This also happened in the 2026-11-24
  run, so it predates today's changes. Those runs had 56–61 failed requests, concentrated on one brand pod (producer46
  and producer76; producer6). The reference answer holds a product of producer76 and of producer6. So the row is most
  likely lost with a failed request: the engine runs with `--lenient`, which skips failed requests silently.
* Derived configurations send more requests on q04 (×1.46), and failed requests are more frequent there. Find which
  requests fail (SPARQL or documents) and why: the jbr runs have `proxyRequestLog: false`.
