"""Narrow HA adapter for the official OpenAI tunnel client."""
import json
import os
import re
import sys
from pathlib import Path




def prepare(options):
    if set(options) != {'tunnel_id', 'runtime_key', 'mail_app_hostname'}:
        raise ValueError('Invalid options')
    tid, key, hostname = (options[x] for x in ('tunnel_id', 'runtime_key', 'mail_app_hostname'))
    if not isinstance(tid, str) or not re.fullmatch(r'tunnel_[0-9a-f]{32}', tid):
        raise ValueError('Invalid tunnel')
    if not isinstance(key, str) or not key.startswith('sk-') or len(key) > 4096 or any(c.isspace() for c in key):
        raise ValueError('Invalid runtime key')
    # Supervisor DNS uses repository prefix + slug, with underscores replaced by hyphens.
    if not isinstance(hostname, str) or not re.fullmatch(r'(?:[0-9a-f]{8}|local)-household-mail', hostname):
        raise ValueError('Only the mail app is allowed')
    return {'CONTROL_PLANE_TUNNEL_ID': tid, 'CONTROL_PLANE_API_KEY': key,
            'MCP_SERVER_URL': f'http://{hostname}:8000/mcp',
            # OAuth metadata uses the existing isolated HA container network.
            'HARPOON_ALLOW_PLAINTEXT_HTTP': 'true',
            'HARPOON_HOSTS_INCLUDE_REGEX': '^' + re.escape(hostname) + ' 'LOG_LEVEL': 'error', 'LOG_FORMAT': 'json'}




def main():
    try:
        settings = prepare(json.loads(Path('/data/options.json').read_text()))
        os.umask(0o077)
        if os.getuid() != 0:
            raise ValueError('Expected bootstrap identity')
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
        env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp', **settings}
        os.execve('/usr/local/bin/tunnel-client', ['tunnel-client', 'run'], env)
    except Exception:,
            'MCP_STARTUP_WAIT_TIMEOUT': '60s',
            'HEALTH_LISTEN_ADDR': '127.0.0.1:8080', 'LOG_LEVEL': 'error', 'LOG_FORMAT': 'json'}




def main():
    try:
        settings = prepare(json.loads(Path('/data/options.json').read_text()))
        os.umask(0o077)
        if os.getuid() != 0:
            raise ValueError('Expected bootstrap identity')
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
        env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp', **settings}
        os.execve('/usr/local/bin/tunnel-client', ['tunnel-client', 'run'], env)
    except Exception:
