#!/usr/bin/env python3
"""
Claude Code PostToolUse hook for Edit|Write.
When editing docker-compose files, checks for ports bound to 0.0.0.0
that should be 127.0.0.1 for internal services.
"""

import json
import re
import sys
from pathlib import Path


# compose file patterns
COMPOSE_PATTERNS = [
    r'docker-compose.*\.ya?ml$',
    r'compose.*\.ya?ml$',
]

# ports that should typically be internal-only
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


def is_compose_file(file_path: str) -> bool:
    """check if the file is a docker-compose file"""
    name = Path(file_path).name
    return any(re.search(p, name) for p in COMPOSE_PATTERNS)


def check_port_bindings(content: str) -> list[str]:
    """scan content for exposed ports that should be internal"""
    issues = []

    # match port mappings in various formats:
    # - "5432:5432"           (bare — defaults to 0.0.0.0)
    # - "0.0.0.0:5432:5432"  (explicit 0.0.0.0)
    # - "127.0.0.1:5432:5432" (safe — skip)

    # pattern: optional "quotes", optional IP, host_port:container_port
    port_pattern = re.compile(
        r'["\']?'                    # optional opening quote
        r'(?:(\d+\.\d+\.\d+\.\d+):)?'  # optional IP binding
        r'(\d+):(\d+)'              # host_port:container_port
        r'(?:/(?:tcp|udp))?'        # optional protocol
        r'["\']?'                    # optional closing quote
    )

    for match in port_pattern.finditer(content):
        ip = match.group(1)
        host_port = int(match.group(2))
        container_port = int(match.group(3))

        # skip if already bound to localhost
        if ip and ip.startswith('127.'):
            continue

        # check if either port is in our internal list
        for port in (host_port, container_port):
            if port in INTERNAL_PORTS:
                service = INTERNAL_PORTS[port]
                if ip == '0.0.0.0':
                    issues.append(
                        f"port {port} ({service}) is explicitly bound to 0.0.0.0 — "
                        f"consider 127.0.0.1:{host_port}:{container_port} for internal services"
                    )
                elif ip is None:
                    issues.append(
                        f"port {port} ({service}) is bound to all interfaces (default) — "
                        f"consider 127.0.0.1:{host_port}:{container_port} for internal services"
                    )
                break

    return issues


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = input_data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')

    if not file_path or not is_compose_file(file_path):
        sys.exit(0)

    content = tool_input.get('new_string', '') or tool_input.get('content', '')
    if not content:
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
