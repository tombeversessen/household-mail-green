# OpenAI mail tunnel configuration

Experimental; container and Supervisor acceptance testing still required.

Create a dedicated Secure MCP Tunnel associated only with the intended personal organization/workspace. Configure its tunnel ID and a runtime API key restricted to Tunnels Read + Use. Never supply an organization admin key. Enter secrets privately in app options.

Set `mail_app_hostname` to the actual hostname of the mail app. The adapter refuses other destinations, including Home Assistant, Supervisor, arbitrary LAN hosts and internet URLs. It forwards only to the mail app on internal port 8000, path /mcp. No host port is published, including the loopback-only health/admin UI.

The official OpenAI tunnel client v0.0.14 is pinned by image digest. This adapter uses the standard outbound HTTPS polling path and does not configure a public Cloudflare hostname or a general network proxy. The deployment operator must verify the actual tunnel behavior, authentication forwarding, readiness, reconnection and token renewal before acceptance.

Keep logs at error level; do not enable raw HTTP tracing on live mailbox traffic. App options and backups can contain the runtime key. Stop this app and revoke its runtime key to withdraw the connection.
