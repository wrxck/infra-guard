# infra-guard

[![CI](https://github.com/wrxck/infra-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/wrxck/infra-guard/actions/workflows/ci.yml)

Infrastructure security enforcement for Claude Code sessions.

## What it checks

- **Nginx security**: HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP validation, TLS version, rate limiting on API endpoints
- **Port exposure**: flags database and internal service ports bound to 0.0.0.0 in docker-compose
- **Infra changes**: detects sensitive configuration changes (timeouts, pool sizes, ports, SSL) in infrastructure files
- **Env sync**: checks .env and .env.example stay in sync

## Commands

- `/harden` -- full project hardening audit with auto-fix suggestions

## Installation

```
claude plugin marketplace add wrxck/claude-plugins
claude plugin install infra-guard@wrxck-claude-plugins
```
