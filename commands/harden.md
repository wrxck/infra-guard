# /harden -- Project Hardening Audit

Audit the target project against production hardening best practices and offer to auto-fix each finding.

## Arguments

- Optional: path to the project directory. Defaults to current working directory.

## Steps

### 1. Identify Target

If an argument was provided, use that path. Otherwise use the current directory. Verify the path exists and contains project files.

### 2. Audit Dockerfile

Look for `Dockerfile` or `Dockerfile.*` in the project. For each Dockerfile, check:

| Check | Severity | Auto-fixable |
|-------|----------|-------------|
| No `USER` directive (running as root) | HIGH | Yes -- add `RUN addgroup -S app && adduser -S app -G app` + `USER app` |
| No `HEALTHCHECK` instruction | MEDIUM | Yes -- add appropriate HEALTHCHECK based on exposed port |
| Using `:latest` or untagged base image | MEDIUM | Suggest specific version |
| Not using alpine/slim variant | LOW | Suggest alternative |
| `npm install` instead of `npm ci` | MEDIUM | Yes -- replace |
| `apt-get` without `--no-install-recommends` | LOW | Yes -- add flag |
| Missing apt cache cleanup | LOW | Yes -- append `&& rm -rf /var/lib/apt/lists/*` |
| Single-stage build where multi-stage would help | LOW | No -- manual |

### 3. Audit docker-compose.yml

Look for `docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, `compose.yaml`. Check each service:

| Check | Severity | Auto-fixable |
|-------|----------|-------------|
| Missing `healthcheck:` | HIGH | Yes -- add based on service type |
| Missing `cap_drop: [ALL]` under `security_opt` | HIGH | Yes -- add |
| Missing `security_opt: [no-new-privileges:true]` | HIGH | Yes -- add |
| Missing `restart: unless-stopped` | MEDIUM | Yes -- add |
| Missing `logging` config | MEDIUM | Yes -- add json-file driver with max-size 10m, max-file 3 |
| Missing `deploy.resources.limits` | MEDIUM | Yes -- add sensible defaults |
| `depends_on` without `condition: service_healthy` | MEDIUM | Yes -- convert to long form |
| Exposed ports that could be internal | LOW | Flag for review |

### 4. Audit Nginx Config

Look for nginx config files (`*.conf`, `nginx/`, `etc/nginx/`). Check:

| Check | Severity | Auto-fixable |
|-------|----------|-------------|
| Missing `Strict-Transport-Security` | HIGH | Yes -- add `add_header` |
| Missing `X-Content-Type-Options: nosniff` | HIGH | Yes -- add |
| Missing `X-Frame-Options` | MEDIUM | Yes -- add DENY or SAMEORIGIN |
| Missing `Referrer-Policy` | MEDIUM | Yes -- add `strict-origin-when-cross-origin` |
| CSP with `unsafe-inline`/`unsafe-eval` | MEDIUM | Flag for review |
| TLS 1.0/1.1 enabled | HIGH | Yes -- restrict to TLSv1.2 TLSv1.3 |
| Missing rate limiting on API endpoints | MEDIUM | Yes -- add `limit_req_zone` and `limit_req` |

### 5. Audit Environment Files

| Check | Severity | Auto-fixable |
|-------|----------|-------------|
| `.env` exists without `.env.example` | MEDIUM | Yes -- generate from .env with values blanked |
| Keys in `.env` missing from `.env.example` | LOW | Yes -- add missing keys |
| `.env` not in `.gitignore` | HIGH | Yes -- add to .gitignore |

### 6. Audit Exposed Ports

Check docker-compose for ports mapped to `0.0.0.0` that should be internal (database ports, admin interfaces). Standard internal ports:
- 5432 (PostgreSQL), 3306 (MySQL), 6379 (Redis), 27017 (MongoDB)
- Admin panels, debug ports

### 7. Produce Report

Format as a severity-sorted table:

```
## Hardening Audit: project-name

### Summary
- HIGH: 3 findings
- MEDIUM: 5 findings
- LOW: 2 findings

### Findings

| # | Severity | File | Finding | Auto-fix? |
|---|----------|------|---------|-----------|
| 1 | HIGH | Dockerfile | Running as root -- no USER directive | Yes |
| 2 | HIGH | docker-compose.yml | Service "app" missing cap_drop ALL | Yes |
| ... | ... | ... | ... | ... |
```

### 8. Offer Auto-fix

After showing the report, ask the user: "Would you like me to auto-fix the fixable findings? I can fix all, or you can choose specific items by number."

Apply fixes one at a time, showing each change before making it. Skip any that need manual review.
