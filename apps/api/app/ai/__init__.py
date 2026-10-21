"""BioNova AI gateway (phase AI-0, docs/AI_ARCHITECTURE.md).

One entry point, :func:`gateway.dispatch`, applies — in order — the kill
switches, the plan entitlement, the tenant opt-in, the data-class ceiling of
the selected provider, credit metering, output validation and the append-only
audit row. The default provider is an in-process mock; nothing leaves the
server unless ``AI_LIVE_ENABLED`` is true AND a provider is configured.
"""
