# Mail connector configuration

Experimental; requires successful ARM64 container and Supervisor acceptance tests.

Enter the mailbox username/password privately in app options. Supports the existing personal account and an optional mum account at `imap.mailprotect.be:993`. Default folder selection is INBOX. Additional folder names must be exact and explicitly selected. OAuth issuer, trusted JWKS URL, resource URL (HTTPS ending in /mcp), allowed subject IDs and allowed client IDs are mandatory. Empty or invalid settings prevent startup.

Set `mail_app_hostname` to this app's actual Supervisor hostname. It is the repository prefix followed by `-household-mail`, with underscores converted to hyphens. Use the same value in the tunnel app. Only this exact extra Host header is allowed. OAuth is still required for internal requests.

The deployment operator must verify tunnel-rewritten OAuth discovery, audience and Host compatibility before connecting a mailbox. Never disable authentication to troubleshoot. Check incorrect-token rejection, account/folder restrictions, unchanged unread status, and refresh-token renewal before scheduled use.

The app reads `/data/options.json` at bootstrap and then runs as UID/GID 10001. Only non-secret account metadata is written to a private temporary file. It has no Home Assistant or Supervisor API privileges. App options and backups can contain credentials; restrict administrator and backup access.

Stopping the app stops mailbox access. No Home Assistant restart is required for normal app configuration changes. Do not enable automatic start until initial acceptance has passed.

## Optional second account (0.1.3)

Existing personal options are unchanged. Leave mum_enabled off until the second
account is configured. Enter mum_username and mum_password privately in the app
options; the password uses the same Supervisor password field and process-only
secret environment mechanism as personal. Neither credential is written to source
or generated account metadata. Start with mum_folders containing only INBOX.
Enable mum, save and restart only the mail app.

list_folders for mum additionally returns server_sent_folders from the server's
special-use \Sent flags. This is metadata discovery only and does not expose those
folders for message access. Add an exact returned folder name to mum_folders only
after successful authentication. Never infer a folder from its name. Empty results
mean no server-declared Sent folder was found. Multiple results require an explicit
administrator choice. All existing read-only IMAP command guards remain active.
