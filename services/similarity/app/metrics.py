from prometheus_client import Counter, Histogram

lookups = Counter(
    "semcache_lookups_total",
    "Lookup outcomes",
    ["result"],
)

lookup_seconds = Histogram(
    "semcache_lookup_seconds",
    "How long /lookup took",
)

stores = Counter(
    "semcache_stores_total",
    "Store outcomes",
    ["result"],
)

# A series that first appears at 1 has no 0 -> 1 step, so increase() stays 0.
for result in ("empty", "hit", "not_a_hit"):
    lookups.labels(result=result).inc(0)
for result in ("ttl_skip", "stored"):
    stores.labels(result=result).inc(0)
