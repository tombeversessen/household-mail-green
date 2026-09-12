# Mail connector configuration

Experimental; requires successful ARM64 container and Supervisor acceptance tests.

Enter the mailbox username/password privately in app options. The first version supports one Combell mailbox at `imap.mailprotect.be:993`. Default folder selection is INBOX. Additional folder names must be exact and explicitly selected. OAuth issuer, trusted JWKS URL, resource URL (HTTPS ending in /mcp), allowed subject IDs and allowed client IDs are mandatory. Empty or invalid settings prevent startup.

Set `mail_app_hostname` to this app's actual Supervisor hostname. It is the repository prefix followed by `-household-mail`, with underscores converted to hyphens. Use the same value in the tunnel app. Only this exact extra Host header is allowed. OAuth is still required for internal requests.

The deployment operator must verify tunnel-rewritten OAuth discovery, audience and Host compatibility before connecting a mailbox. Never disable authentication to troubleshoot. Check incorrect-token rejection, account/folder restrictions, unchanged unread status, and refresh-token renewal before scheduled use.

The app reads `/data/options.json` at bootstrap and then runs as UID/GID 10001. Only non-secret account metadata is written to a private temporary file. It has no Home Assistant or Supervisor API privileges. App options and backups can contain credentials; restrict administrator and backup access.

Stopping the app stops mailbox access. No Home Assistant restart is required for normal app configuration changes. Do not enable automatic start until initial acceptance has passed.
