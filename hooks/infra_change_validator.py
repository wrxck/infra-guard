#!/usr/bin/env python3
"""
Claude Code PostToolUse hook for Edit|Write|MultiEdit.
Detects edits to infrastructure-sensitive files and reminds Claude
to validate defaults and test before deploying.
"""

import json
import re
import sys
from pathlib import Path


INFRA_PATTERNS = [
    r'docker-compose.*\.ya?ml$',
    r'compose.*\.ya?ml$',
    r'Dockerfile',
    r'\.env(\.|$)',
    r'nginx\.conf',
    r'\.config\.(ts|js|mjs|cjs)$',
    r'config\.(hpp|cpp|h|c)$',
    r'proxy.*\.(hpp|cpp|h|c|ts|js)$',
    r'Caddyfile$',
    r'traefik.*\.ya?ml$',
    r'haproxy\.cfg$',
    r'supervisord\.conf$',
    r'systemd/.*\.service$',
]


SENSITIVE_CHANGES = [
    (r'(?m)^[^#\n]*?\b(timeout|TIMEOUT)\s*[=:]\s*\d+\b', 'timeout value changed'),
    (r'\b(pool_size|poolSize|max_connections|maxConnections)\s*[=:]\s*\d+\b', 'connection pool size changed'),
    (r'(?m)^[^#\n]*?\b(port|PORT)\b\s*[=:]\s*\d+\b(?![^\s]*://)', 'port configuration changed'),
    (r'\blisten\s+\d+\b', 'nginx listen directive changed'),
    (r'(?im)^\s*EXPOSE\s+\d+\b', 'Dockerfile EXPOSE directive changed'),
    (r'\b(HOST|host)\s*[=:]\s*["\']?\d+\.\d+\.\d+\.\d+', 'host binding changed'),
    (r'\b(workers|WORKERS|threads|THREADS)\s*[=:]\s*\d+\b', 'worker/thread count changed'),
    (r'\b(mem_limit|memswap_limit)\s*[=:]', 'memory limit changed'),
    (r'(?m)^\s*replicas\s*:\s*\d+\b', 'replica count changed'),
    (r'\bssl_protocols\b', 'SSL/TLS protocol configuration changed'),
]


def is_infra_file(file_path: str) -> bool:
    name = Path(file_path).name
    return any(re.search(p, name) or re.search(p, file_path) for p in INFRA_PATTERNS)


def detect_sensitive_changes(content: str) -> list[str]:
    findings = []
    seen = set()
    for pattern, description in SENSITIVE_CHANGES:
        if re.search(pattern, content):
            if description not in seen:
                findings.append(description)
                seen.add(description)
    return findings


def collect_content(tool_input: dict) -> str:
    parts = []
    if tool_input.get('new_string'):
        parts.append(tool_input['new_string'])
    if tool_input.get('content'):
        parts.append(tool_input['content'])
    for edit in tool_input.get('edits', []) or []:
        if isinstance(edit, dict) and edit.get('new_string'):
            parts.append(edit['new_string'])
    return '\n'.join(parts)


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = input_data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')
    if not file_path or not is_infra_file(file_path):
        sys.exit(0)

    content = collect_content(tool_input)
    if not content:
        sys.exit(0)

    findings = detect_sensitive_changes(content)
    if not findings:
        sys.exit(0)

    lines = [f"infrastructure file modified: {Path(file_path).name}"]
    lines.append("sensitive changes detected:")
    for f in findings:
        lines.append(f"  - {f}")
    lines.append("")
    lines.append(
        "verify defaults are production-safe and test before deploying."
    )

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
