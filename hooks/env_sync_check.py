#!/usr/bin/env python3
"""
Claude Code PostToolUse hook for Edit|Write.
Checks that .env and .env.example files stay in sync:
- When .env is edited, checks .env.example has matching keys
- When .env.example is edited, checks .env has matching keys
- Flags keys present in one but not the other
"""

import json
import os
import re
import sys
from pathlib import Path


def is_env_file(file_path: str) -> bool:
    """check if file is a .env variant"""
    name = Path(file_path).name
    return name in ('.env', '.env.example', '.env.local', '.env.development', '.env.production')


def extract_keys(content: str) -> set[str]:
    """extract environment variable keys from .env content"""
    keys = set()
    for line in content.split('\n'):
        stripped = line.strip()
        # skip comments and empty lines
        if not stripped or stripped.startswith('#'):
            continue
        # extract key from KEY=value or KEY= or export KEY=value
        match = re.match(r'^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=', stripped)
        if match:
            keys.add(match.group(1))
    return keys


def read_file_keys(file_path: str) -> set[str] | None:
    """read a file and extract its env keys, returns None if file doesn't exist"""
    try:
        with open(file_path, 'r') as f:
            return extract_keys(f.read())
    except (FileNotFoundError, PermissionError):
        return None


def check_env_sync(file_path: str, content: str) -> list[str]:
    """check env file sync issues"""
    issues = []
    name = Path(file_path).name
    directory = str(Path(file_path).parent)

    edited_keys = extract_keys(content)

    if name == '.env' or name == '.env.local':
        # check against .env.example
        example_path = os.path.join(directory, '.env.example')
        example_keys = read_file_keys(example_path)

        if example_keys is None:
            if edited_keys:
                issues.append(f'no .env.example found alongside {name} — consider creating one for documentation')
        else:
            # keys in .env but not in .env.example
            missing_from_example = edited_keys - example_keys
            if missing_from_example:
                issues.append(f'keys in {name} but missing from .env.example: {", ".join(sorted(missing_from_example))}')

            # keys in .env.example but not in .env
            missing_from_env = example_keys - edited_keys
            if missing_from_env:
                issues.append(f'keys in .env.example but missing from {name}: {", ".join(sorted(missing_from_env))}')

    elif name == '.env.example':
        # check against .env
        env_path = os.path.join(directory, '.env')
        env_keys = read_file_keys(env_path)

        if env_keys is not None:
            # keys in .env.example but not in .env
            missing_from_env = edited_keys - env_keys
            if missing_from_env:
                issues.append(f'keys in .env.example but missing from .env: {", ".join(sorted(missing_from_env))}')

            # keys in .env but not in .env.example
            missing_from_example = env_keys - edited_keys
            if missing_from_example:
                issues.append(f'keys in .env but missing from .env.example: {", ".join(sorted(missing_from_example))}')

    return issues


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = input_data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')

    if not file_path or not is_env_file(file_path):
        sys.exit(0)

    content = tool_input.get('new_string', '') or tool_input.get('content', '')
    if not content:
        sys.exit(0)

    issues = check_env_sync(file_path, content)

    if issues:
        lines = ['env file sync check:']
        for issue in issues:
            lines.append(f'  - {issue}')
        lines.append('')
        lines.append('keep .env and .env.example in sync so fresh clones work correctly.')

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
