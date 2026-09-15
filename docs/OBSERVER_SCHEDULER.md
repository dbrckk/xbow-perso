# Incident observer scheduling

The observer is designed as a single-pass function. Periodic timing remains outside the incident engine.

## Leader lease

A small SQLite lease provides shared-database leader exclusion. Only one owner can hold a non-expired lease.

Default configuration:

- observation interval: 30 seconds;
- leader lease TTL: 90 seconds.

The TTL must be at least twice the configured interval. Invalid configuration fails closed.

## Failover

An expired lease can be acquired by another instance. The lease is also released after a normal observation pass.

The lease does not grant permission to execute campaign work. It gates incident observation only.

## Deployment

An external scheduler, service timer, or controlled application task can invoke one observation pass at the configured interval. Each invocation should use a stable per-process owner identifier.

Do not run an unbounded scheduler loop inside request handlers.

## Safety

Leadership affects only operational observation. The scheduler cannot create jobs, reclaim worker leases, restart scanners, modify target scope, or change campaign authorization.
