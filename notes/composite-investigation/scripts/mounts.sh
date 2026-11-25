# Prints ENGINE_MOUNTS for the local engine: storage fix + SteMs changes + bound-composite actors + CPU fixes (compiled JS)
NM=/var/www/@comunica/query-sparql-link-traversal-solid/node_modules/@comunica
S=$HOME/projects/query-derived-resources/comunica-adaptive-derived-resources/packages/actor-rdf-join-inner-multi-stems/lib
L=$HOME/projects/query-derived-resources/comunica-feature-link-traversal-adaptive-derived-resources/packages
W=$HOME/projects/query-derived-resources/benchmark-experiments/jbr-experiment-fedshop-discovery-enable-proxy-tracking/input/overrides/wrapper-prioritize-derived-resources-and-datasets.json
m=()
m+=("$W:$NM/config-query-sparql-link-traversal/config/rdf-resolve-hypermedia-links-queue/actors/wrapper-prioritize-derived-resources-and-datasets.json:ro")
for f in ActorRdfJoinMultiStems.js StemsTimeseries.js StemsControllerStream.js StemsOperatorStream.js filters/CompositeClaim.js filters/DelegatedPatternsFilter.js filters/DelegatedPatternsFilterIndex.js; do
  m+=("$S/$f:$NM/actor-rdf-join-inner-multi-stems/lib/$f:ro"); done
for f in ActorDerivedResourceExecuteCompositeSource.js BoundCompositeCoordinator.js FilterPushdown.js index.js; do
  m+=("$L/actor-derived-resource-execute-composite-source/lib/$f:$NM/actor-derived-resource-execute-composite-source/lib/$f:ro"); done
m+=("$L/actor-derived-resource-partition-star-first/lib/ActorDerivedResourcePartitionStarFirst.js:$NM/actor-derived-resource-partition-star-first/lib/ActorDerivedResourcePartitionStarFirst.js:ro")
m+=("$L/bus-derived-resource-execute/lib/ActorDerivedResourceExecute.js:$NM/bus-derived-resource-execute/lib/ActorDerivedResourceExecute.js:ro")  # DERIVED_SKIP_SINGLE_BLOCKS
# CPU fixes (2026-11-23): one shared SPARQL parser for all SPARQL sources; link extractor patterns cached per query
C=$HOME/projects/query-derived-resources/comunica-adaptive-derived-resources/packages
m+=("$C/actor-query-source-identify-hypermedia-sparql/lib/QuerySourceSparql.js:$NM/actor-query-source-identify-hypermedia-sparql/lib/QuerySourceSparql.js:ro")
m+=("$L/actor-extract-links-quad-pattern-query/lib/ActorExtractLinksQuadPatternQuery.js:$NM/actor-extract-links-quad-pattern-query/lib/ActorExtractLinksQuadPatternQuery.js:ro")
# Lower links into a dataset whose document is still to be handled (2026-11-23)
m+=("$L/actor-rdf-resolve-hypermedia-links-queue-priority-wrapper-derived-resource/lib/LinkQueueDerivedResourcePrioritization.js:$NM/actor-rdf-resolve-hypermedia-links-queue-priority-wrapper-derived-resource/lib/LinkQueueDerivedResourcePrioritization.js:ro")
m+=("$L/actor-rdf-resolve-hypermedia-links-queue-priority-wrapper-derived-resource/lib/ActorRdfResolveHypermediaLinksQueuePriorityWrapperDerivedResource.js:$NM/actor-rdf-resolve-hypermedia-links-queue-priority-wrapper-derived-resource/lib/ActorRdfResolveHypermediaLinksQueuePriorityWrapperDerivedResource.js:ro")
m+=("$L/actor-context-preprocess-set-dynamic-links-filter/lib/DynamicLinksFilter.js:$NM/actor-context-preprocess-set-dynamic-links-filter/lib/DynamicLinksFilter.js:ro")
m+=("$L/actor-extract-links-solid-derived-resources/lib/ActorExtractLinksSolidDerivedResources.js:$NM/actor-extract-links-solid-derived-resources/lib/ActorExtractLinksSolidDerivedResources.js:ro")
(IFS=,; echo "${m[*]}")
