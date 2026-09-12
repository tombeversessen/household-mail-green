"""Read Supervisor options before dropping privileges; never print option values."""
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from household_imap.config import Account, AuthConfig, MailConfig


def prepare(options):
    expected = {'mailbox_username', 'mailbox_password', 'folders', 'resource_url',
                'oauth_issuer', 'oauth_jwks_url', 'allowed_subjects', 'allowed_client_ids', 'mail_app_hostname'}
    if set(options) != expected:
        raise ValueError('Invalid configuration')
    for key in ('mailbox_username', 'mailbox_password'):
        if not isinstance(options[key], str) or not options[key] or len(options[key]) > 4096:
            raise ValueError('Missing mailbox configuration')
    hostname = options['mail_app_hostname']
    if not isinstance(hostname, str) or not re.fullmatch(r'(?:[0-9a-f]{8}|local)-household-mail', hostname):
        raise ValueError('Invalid internal hostname')
    auth = AuthConfig(resource=options['resource_url'], issuer=options['oauth_issuer'],
                      jwks_url=options['oauth_jwks_url'],
                      allowed_subjects=options['allowed_subjects'],
                      allowed_client_ids=options['allowed_client_ids'])
    for entries in (auth.allowed_subjects, auth.allowed_client_ids):
        if any(not s or any(c.isspace() for c in s) for s in entries):
            raise ValueError('Invalid identity selection')
    account = Account(id='personal', label='Persoonlijke Combell-mail', enabled=True,
                      username_env='IMAP_PERSONAL_USERNAME', password_env='IMAP_PERSONAL_PASSWORD',
                      folders=options['folders'], airmail_flag_verified=False)
    config = MailConfig(accounts=[account])
    env = {'IMAP_PERSONAL_USERNAME': options['mailbox_username'],
           'IMAP_PERSONAL_PASSWORD': options['mailbox_password'],
           'MCP_RESOURCE_URL': auth.resource, 'OAUTH_ISSUER': auth.issuer,
           'OAUTH_JWKS_URL': auth.jwks_url,
           'OAUTH_ALLOWED_SUBJECTS': ' '.join(auth.allowed_subjects),
           'OAUTH_ALLOWED_CLIENT_IDS': ' '.join(auth.allowed_client_ids), 'PORT': '8000', 'IMAP_INTERNAL_HOST': hostname}
    return config, env


def main():
    try:
        config, secrets = prepare(json.loads(Path('/data/options.json').read_text()))
        os.umask(0o077)
        if os.getuid() != 0:
            raise ValueError('Expected bootstrap identity')
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
        # Only non-secret account metadata is written; /tmp is container-local.
        with tempfile.NamedTemporaryFile(mode='w', prefix='imap-', suffix='.json', delete=False) as f:
            f.write(config.model_dump_json())
            config_path = f.name
        env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp',
               'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
               'IMAP_CONFIG_FILE': config_path, **secrets}
        os.execve('/usr/local/bin/household-imap', ['household-imap'], env)
    except Exception:
        print('Startup refused: check app configuration and required secrets.', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
