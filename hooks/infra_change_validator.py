#!/usr/bin/env python3
"""
Claude Code PostToolUse hook for Edit|Write.
Detects edits to infrastructure-sensitive files and reminds Claude
to validate defaults and test before deploying.
"""

import json
import re
import sys
from pathlib import Path


# file patterns considered infrastructure-sensitive
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

# patterns in diff content that warrant extra attention
SENSITIVE_CHANGES = [
    (r'\b(timeout|TIMEOUT)\s*[=:]\s*\d+', 'timeout value changed'),
    (r'\b(pool_size|poolSize|max_connections|maxConnections)\s*[=:]\s*\d+', 'connection pool size changed'),
    (r'\b(port|PORT)\s*[=:]\s*\d+', 'port configuration changed'),
    (r'\b(host|HOST)\s*[=:]\s*["\']?\d+\.\d+\.\d+\.\d+', 'host binding changed'),
    (r'\b(workers|WORKERS|threads|THREADS)\s*[=:]\s*\d+', 'worker/thread count changed'),
    (r'\b(memory|MEMORY|mem_limit)\s*[=:]', 'memory limit changed'),
    (r'\b(replicas|REPLICAS)\s*[=:]\s*\d+', 'replica count changed'),
    (r'\benvironment\s*:', 'environment variables section modified'),
    (r'\bvolumes\s*:', 'volumes section modified'),
    (r'\bnetworks\s*:', 'networks section modified'),
    (r'\b(ssl|tls|SSL|TLS)\b', 'SSL/TLS configuration changed'),
]


def is_infra_file(file_path: str) -> bool:
    """check if the file is infrastructure-sensitive"""
    name = Path(file_path).name
    full = file_path
    return any(re.search(p, name) or re.search(p, full) for p in INFRA_PATTERNS)


def detect_sensitive_changes(content: str) -> list[str]:
    """scan content for sensitive configuration patterns"""
    findings = []
    for pattern, description in SENSITIVE_CHANGES:
        if re.search(pattern, content):
            findings.append(description)
    return findings


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = input_data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')

    if not file_path or not is_infra_file(file_path):
        sys.exit(0)

    # get the content that was written/edited
    content = tool_input.get('new_string', '') or tool_input.get('content', '')
    if not content:
        sys.exit(0)

    findings = detect_sensitive_changes(content)

    lines = [f"infrastructure file modified: {Path(file_path).name}"]
    if findings:
        lines.append("sensitive changes detected:")
        for f in findings:
            lines.append(f"  - {f}")
    lines.append("")
    lines.append(
        "verify defaults are production-safe and test before deploying. "
        "check that timeouts, pool sizes, and port bindings are appropriate "
        "for the target environment."
    )

    context = '\n'.join(lines)
    output = {
        'hookSpecificOutput': {
            'hookEventName': 'PostToolUse',
            'additionalContext': context,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == '__main__':
    main()
