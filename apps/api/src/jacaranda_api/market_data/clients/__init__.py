"""Live (network-capable) client implementations for the market-data adapter protocols.

These are the only market-data modules that touch real SDKs. They are never
imported by tests or CI paths; adapters receive them by injection.
"""
