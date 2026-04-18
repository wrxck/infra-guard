#!/usr/bin/env python3
"""
Claude Code PostToolUse hook for Edit|Write|MultiEdit.
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


ENV_NAME_RE = re.compile(r'^\.env(?:[.-][-\w]+)?$')


def is_env_file(file_path: str) -> bool:
    name = Path(file_path).name
    return bool(ENV_NAME_RE.match(name))


def extract_keys(content: str) -> set[str]:
    keys = set()
    for line in content.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        match = re.match(r'^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=', stripped)
        if match:
            keys.add(match.group(1))
    return keys


def read_file_keys(file_path: str) -> set[str] | None:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return extract_keys(f.read())
    except (FileNotFoundError, PermissionError):
        return None


def check_env_sync(file_path: str, content: str) -> list[str]:
    issues = []
    name = Path(file_path).name
    directory = str(Path(file_path).parent)

    edited_keys = extract_keys(content)

    if name == '.env.example':
        env_path = os.path.join(directory, '.env')
        env_keys = read_file_keys(env_path)
        if env_keys is not None:
            missing_from_env = edited_keys - env_keys
            if missing_from_env:
                issues.append(f'keys in .env.example but missing from .env: {", ".join(sorted(missing_from_env))}')
            missing_from_example = env_keys - edited_keys
            if missing_from_example:
                issues.append(f'keys in .env but missing from .env.example: {", ".join(sorted(missing_from_example))}')
        return issues

    example_path = os.path.join(directory, '.env.example')
    example_keys = read_file_keys(example_path)

    if example_keys is None:
        if edited_keys:
            issues.append(f'no .env.example found alongside {name} - consider creating one for documentation')
        return issues

    missing_from_example = edited_keys - example_keys
    if missing_from_example:
        issues.append(f'keys in {name} but missing from .env.example: {", ".join(sorted(missing_from_example))}')

    missing_from_env = example_keys - edited_keys
    if missing_from_env:
        issues.append(f'keys in .env.example but missing from {name}: {", ".join(sorted(missing_from_env))}')

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
    if not file_path or not is_env_file(file_path):
        sys.exit(0)

    disk_content = read_disk(file_path)
    fragment = collect_content(tool_input)
    content = disk_content if disk_content else fragment
    if not content:
        sys.exit(0)

    issues = check_env_sync(file_path, content)
    if not issues:
        sys.exit(0)

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
