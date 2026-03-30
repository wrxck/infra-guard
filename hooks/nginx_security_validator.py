#!/usr/bin/env python3
"""
Claude Code PostToolUse hook for Edit|Write.
Validates nginx config files for security best practices:
- HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy
- CSP with unsafe-inline/unsafe-eval
- TLS 1.0/1.1
- proxy_pass to non-HTTPS upstream
- missing rate limiting for API locations
"""

import json
import re
import sys
from pathlib import Path


def is_nginx_config(file_path: str, content: str) -> bool:
    """check if file is an nginx config"""
    name = Path(file_path).name
    if not name.endswith('.conf'):
        return False
    # must contain nginx-like directives
    return bool(re.search(r'\b(server\s*\{|location\s|proxy_pass\s|upstream\s)', content))


def check_security(content: str, file_path: str) -> list[str]:
    """check nginx config for security issues"""
    issues = []

    # only check server blocks (not upstream-only configs)
    if not re.search(r'\bserver\s*\{', content):
        return issues

    # check for HSTS
    if not re.search(r'Strict-Transport-Security', content):
        issues.append('missing Strict-Transport-Security header (HSTS)')

    # check for X-Content-Type-Options
    if not re.search(r'X-Content-Type-Options', content):
        issues.append('missing X-Content-Type-Options: nosniff header')

    # check for X-Frame-Options
    if not re.search(r'X-Frame-Options', content):
        issues.append('missing X-Frame-Options header')

    # check for Referrer-Policy
    if not re.search(r'Referrer-Policy', content):
        issues.append('missing Referrer-Policy header')

    # check CSP for unsafe-inline/unsafe-eval in script-src
    csp_match = re.search(r'Content-Security-Policy[^;]*', content)
    if csp_match:
        csp = csp_match.group(0)
        if re.search(r"script-src[^;]*'unsafe-inline'", csp):
            issues.append("CSP script-src contains 'unsafe-inline' — consider using nonces or hashes")
        if re.search(r"script-src[^;]*'unsafe-eval'", csp):
            issues.append("CSP script-src contains 'unsafe-eval' — avoid if possible")

    # check for TLS 1.0 or 1.1
    if re.search(r'ssl_protocols\s[^;]*(TLSv1\.0|TLSv1\.1)', content):
        issues.append('SSL config allows TLS 1.0 or 1.1 — use TLSv1.2 TLSv1.3 only')

    # check proxy_pass to HTTP (not HTTPS) upstream, excluding localhost/127.0.0.1
    for match in re.finditer(r'proxy_pass\s+http://([^/;\s]+)', content):
        host = match.group(1).split(':')[0]
        if host not in ('localhost', '127.0.0.1', '::1') and not host.startswith('unix:'):
            issues.append(f'proxy_pass to http://{match.group(1)} — consider HTTPS unless this is an internal service')

    # check for rate limiting on API locations
    api_locations = re.findall(r'location\s+(?:~\s+)?(/api\b[^{]*)\{([^}]*)\}', content, re.DOTALL)
    for path, block in api_locations:
        if not re.search(r'limit_req\b', block):
            issues.append(f'API location {path.strip()} has no rate limiting (limit_req)')

    return issues


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = input_data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')

    if not file_path:
        sys.exit(0)

    content = tool_input.get('new_string', '') or tool_input.get('content', '')
    if not content:
        sys.exit(0)

    if not is_nginx_config(file_path, content):
        sys.exit(0)

    issues = check_security(content, file_path)

    if issues:
        lines = [f'nginx security review for {Path(file_path).name}:']
        for issue in issues:
            lines.append(f'  - {issue}')
        lines.append('')
        lines.append('consider adding missing security headers before deploying.')

        output = {
            'hookSpecificOutput': {
                'hookEventName': 'PostToolUse',
                'additionalContext': '\n'.join(lines),
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == '__main__':
    main()
