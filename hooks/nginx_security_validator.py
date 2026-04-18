#!/usr/bin/env python3
"""
Claude Code PostToolUse hook for Edit|Write|MultiEdit.
Validates nginx config files for security best practices:
- HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy
- CSP with unsafe-inline/unsafe-eval
- TLS 1.0/1.1
- proxy_pass to non-HTTPS upstream
- missing rate limiting for API locations
"""

import json
import os
import re
import sys
from pathlib import Path


NGINX_DIR_HINTS = (
    '/etc/nginx/',
    'nginx/sites-available/',
    'nginx/sites-enabled/',
    'nginx/conf.d/',
)


def is_nginx_config(file_path: str, content: str) -> bool:
    name = Path(file_path).name
    normalised = file_path.replace('\\', '/')
    looks_like_path = name.endswith('.conf') or any(h in normalised for h in NGINX_DIR_HINTS)
    if not looks_like_path:
        return False
    return bool(re.search(r'\b(server\s*\{|location\s|proxy_pass\s|upstream\s|http\s*\{)', content))


def find_blocks(content: str, keyword: str) -> list[tuple[str, str]]:
    """return list of (header, body) for every top-level block matching keyword.
    header is the text before the opening brace, body is the content between
    matching braces with nesting preserved."""
    results = []
    i = 0
    n = len(content)
    pattern = re.compile(r'\b' + re.escape(keyword) + r'\b')
    while i < n:
        m = pattern.search(content, i)
        if not m:
            break
        brace = content.find('{', m.end())
        if brace == -1:
            break
        header = content[m.start():brace]
        depth = 1
        j = brace + 1
        while j < n and depth > 0:
            c = content[j]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            j += 1
        if depth == 0:
            body = content[brace + 1:j - 1]
            results.append((header, body))
            i = j
        else:
            break
    return results


def http_scope_text(content: str) -> str:
    blocks = find_blocks(content, 'http')
    if not blocks:
        return ''
    parts = []
    for _, body in blocks:
        parts.append(body)
    return '\n'.join(parts)


def check_server_block(body: str, server_header: str, enclosing_http: str) -> list[str]:
    issues = []

    if not re.search(r'Strict-Transport-Security', body):
        issues.append('missing Strict-Transport-Security header (HSTS)')

    if not re.search(r'X-Content-Type-Options', body):
        issues.append('missing X-Content-Type-Options: nosniff header')

    if not re.search(r'X-Frame-Options', body):
        issues.append('missing X-Frame-Options header')

    if not re.search(r'Referrer-Policy', body):
        issues.append('missing Referrer-Policy header')

    csp_match = re.search(r'Content-Security-Policy[^;]*', body)
    if csp_match:
        csp = csp_match.group(0)
        if re.search(r"script-src[^;]*'unsafe-inline'", csp):
            issues.append("CSP script-src contains 'unsafe-inline' - consider nonces or hashes")
        if re.search(r"script-src[^;]*'unsafe-eval'", csp):
            issues.append("CSP script-src contains 'unsafe-eval' - avoid if possible")

    tls_source = body + '\n' + enclosing_http
    if re.search(r'ssl_protocols\s[^;]*(TLSv1\.0|TLSv1\.1)', tls_source):
        issues.append('SSL config allows TLS 1.0 or 1.1 - use TLSv1.2 TLSv1.3 only')

    for match in re.finditer(r'proxy_pass\s+http://([^/;\s]+)', body):
        host_part = match.group(1)
        host = host_part.split(':')[0]
        if host not in ('localhost', '127.0.0.1', '::1') and not host.startswith('unix:'):
            issues.append(f'proxy_pass to http://{host_part} - consider HTTPS unless internal')

    location_blocks = find_blocks(body, 'location')
    for loc_header, loc_body in location_blocks:
        header_clean = loc_header.strip()
        if not re.search(r'/api\b', header_clean):
            continue
        if re.search(r'\blimit_req\b', loc_body):
            continue
        if re.search(r'\blimit_req\b', body):
            continue
        if re.search(r'\blimit_req\b', enclosing_http):
            continue
        issues.append(f'API location {header_clean} has no rate limiting (limit_req)')

    return issues


def check_security(content: str) -> list[str]:
    issues = []
    server_blocks = find_blocks(content, 'server')
    if not server_blocks:
        return issues

    http_text = http_scope_text(content)

    for idx, (server_header, body) in enumerate(server_blocks, 1):
        block_issues = check_server_block(body, server_header, http_text)
        label = f'server block #{idx}' if len(server_blocks) > 1 else 'server block'
        for issue in block_issues:
            issues.append(f'{label}: {issue}')

    return issues


def collect_content(tool_input: dict) -> str:
    parts = []
    if 'new_string' in tool_input and tool_input['new_string']:
        parts.append(tool_input['new_string'])
    if 'content' in tool_input and tool_input['content']:
        parts.append(tool_input['content'])
    for edit in tool_input.get('edits', []) or []:
        ns = edit.get('new_string') if isinstance(edit, dict) else None
        if ns:
            parts.append(ns)
    return '\n'.join(parts)


def read_disk(file_path: str) -> str:
    try:
        if file_path and os.path.isfile(file_path):
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
    except (OSError, PermissionError):
        return ''
    return ''


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = input_data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')
    if not file_path:
        sys.exit(0)

    disk_content = read_disk(file_path)
    fragment = collect_content(tool_input)

    content = disk_content if disk_content else fragment
    if not content:
        sys.exit(0)

    if not is_nginx_config(file_path, content):
        sys.exit(0)

    issues = check_security(content)
    if not issues:
        sys.exit(0)

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
