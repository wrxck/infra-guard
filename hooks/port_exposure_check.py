#!/usr/bin/env python3
"""
Claude Code PostToolUse hook for Edit|Write|MultiEdit.
When editing docker-compose files, checks for ports bound to 0.0.0.0
that should be 127.0.0.1 for internal services.
"""

import json
import os
import re
import sys
from pathlib import Path


INTERNAL_PORTS = {
    5432: 'PostgreSQL',
    3306: 'MySQL',
    3307: 'MariaDB',
    6379: 'Redis',
    27017: 'MongoDB',
    9090: 'Prometheus',
    9200: 'Elasticsearch',
    9300: 'Elasticsearch transport',
    5672: 'RabbitMQ',
    15672: 'RabbitMQ management',
    2181: 'Zookeeper',
    8500: 'Consul',
    8300: 'Consul server',
    11211: 'Memcached',
    26379: 'Redis Sentinel',
    7474: 'Neo4j',
    8529: 'ArangoDB',
    28015: 'RethinkDB',
    4369: 'Erlang EPMD',
}


INTERPOLATION_RE = re.compile(r'\$\{[^:}]+(?::[-?][^}]*)?\}')


def is_compose_file(file_path: str, content: str) -> bool:
    name = Path(file_path).name.lower()
    if not (name.endswith('.yml') or name.endswith('.yaml')):
        return False
    if re.match(r'^(docker-compose|compose)', name):
        return True
    if content and re.search(r'(?m)^services\s*:', content):
        return True
    return False


def strip_interpolation(value: str) -> str:
    def replace(m: re.Match) -> str:
        text = m.group(0)
        dash = text.find(':-')
        if dash != -1:
            end = text.rfind('}')
            if end > dash + 2:
                return text[dash + 2:end]
        return ''
    return INTERPOLATION_RE.sub(replace, value)


def parse_port_entry(raw: str) -> tuple[str | None, int | None, int | None]:
    """parse a single ports: list entry. returns (ip_binding, host_port, container_port).
    host_port may be None for bare container-only short form (that still binds to 0.0.0.0).
    container_port may be None for bare host entries."""
    value = raw.strip().strip('"').strip("'")
    if not value:
        return (None, None, None)
    value = strip_interpolation(value)
    value = value.split('/', 1)[0]
    parts = value.split(':')

    def to_int(s: str) -> int | None:
        s = s.strip()
        if not s:
            return None
        if '-' in s:
            s = s.split('-', 1)[0]
        try:
            return int(s)
        except ValueError:
            return None

    if len(parts) == 1:
        p = to_int(parts[0])
        return (None, p, p)
    if len(parts) == 2:
        return (None, to_int(parts[0]), to_int(parts[1]))
    if len(parts) >= 3:
        ip = parts[0].strip()
        return (ip, to_int(parts[1]), to_int(parts[2]))
    return (None, None, None)


def extract_port_entries(content: str) -> list[str]:
    """collect raw port entries from every `ports:` list we find."""
    entries = []
    lines = content.split('\n')
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        m = re.match(r'^(\s*)ports\s*:\s*(.*)$', line)
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        remainder = m.group(2).strip()
        if remainder.startswith('['):
            bracket = remainder
            j = i
            while bracket.count('[') > bracket.count(']') and j + 1 < n:
                j += 1
                bracket += '\n' + lines[j]
            inner = bracket[bracket.find('[') + 1:bracket.rfind(']')] if ']' in bracket else bracket[bracket.find('[') + 1:]
            for item in inner.split(','):
                item = item.strip().strip('"').strip("'")
                if item:
                    entries.append(item)
            i = j + 1
            continue
        j = i + 1
        while j < n:
            sub = lines[j]
            if not sub.strip():
                j += 1
                continue
            leading = len(sub) - len(sub.lstrip())
            if leading <= indent and sub.strip():
                break
            item_match = re.match(r'\s*-\s*(.*)$', sub)
            if not item_match:
                break
            raw = item_match.group(1).strip()
            if ':' in raw and not (raw.startswith('"') or raw.startswith("'") or raw[0].isdigit() or raw.startswith('${')):
                break
            raw = raw.rstrip(',').strip().strip('"').strip("'")
            if raw:
                entries.append(raw)
            j += 1
        i = j
    return entries


def check_port_bindings(content: str) -> list[str]:
    issues = []
    entries = extract_port_entries(content)
    for entry in entries:
        ip, host_port, container_port = parse_port_entry(entry)
        if host_port is None and container_port is None:
            continue
        if ip and (ip.startswith('127.') or ip == '::1'):
            continue
        if host_port is None:
            continue
        if host_port not in INTERNAL_PORTS:
            continue
        service = INTERNAL_PORTS[host_port]
        if ip == '0.0.0.0':
            suggestion = f'127.0.0.1:{host_port}:{container_port}' if container_port else f'127.0.0.1:{host_port}'
            issues.append(
                f"port {host_port} ({service}) explicitly bound to 0.0.0.0 - consider {suggestion}"
            )
        elif ip is None:
            suggestion = f'127.0.0.1:{host_port}:{container_port}' if container_port else f'127.0.0.1:{host_port}'
            issues.append(
                f"port {host_port} ({service}) bound to all interfaces (default) - consider {suggestion}"
            )
    return issues


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

    if not is_compose_file(file_path, content):
        sys.exit(0)

    issues = check_port_bindings(content)
    if not issues:
        sys.exit(0)

    lines = ["port exposure warning for docker-compose file:"]
    for issue in issues:
        lines.append(f"  - {issue}")
    lines.append("")
    lines.append(
        "database and internal service ports should generally be bound to "
        "127.0.0.1 to prevent external access."
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
