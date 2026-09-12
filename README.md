# Household Mail Green

Experimental Home Assistant apps for a private, read-only IMAP MCP connector.

- `household_mail`: one explicitly selected Combell IMAP mailbox over verified TLS; OAuth required.
- `openai_mail_tunnel`: OpenAI Secure MCP Tunnel client with a fixed internal mail-app destination.

No host ports, device access, Home Assistant API access, Supervisor API access or shared Home Assistant configuration are requested. Protected mode remains enabled. Both apps start manually until acceptance testing is complete.

## Status

Both complete ARM64 container images built successfully in [GitHub Actions](https://github.com/tombeversessen/household-mail-green/actions/runs/34714680648), and all 60 software tests passed on ARM64. Tunnel startup and safe rejection of empty configurations also passed. Home Assistant recognizes both apps. Installation, live authentication, mailbox access and scheduled ChatGPT use still require acceptance testing; this is not yet an operational deployment.

This repository contains software only. Configure secrets in Home Assistant app options, never in Git. Options and backups remain accessible to appropriately privileged Home Assistant administrators.

## Installation

Add this repository URL in Home Assistant's app-store repository settings after the ARM64 build checks pass. Install the mail and tunnel apps without starting them. The deployment operator must set up OAuth, a dedicated OpenAI tunnel, a restricted runtime key, the internal app hostname and an explicit mailbox/folder selection before starting either app. See each app's Documentation tab.

Only read-only mailbox operations are implemented. Airmail-star mapping remains unverified until a controlled star/unstar check is performed. No scheduling is created by this package.
