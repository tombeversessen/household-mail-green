"""Administrator-only diagnostics. Never exposed as MCP tools."""
import argparse
import getpass
import json
import logging
import os
import sys

from .config import MailConfig
from .mail import MailService, MailError, MessageRef


def flags_only(service, ref):
    account = service.account(ref.account)
    service.targets([ref.account], [ref.folder])
    with service.connection(account) as client:
        if service.select(client, ref.folder) != ref.uidvalidity:
            raise MailError("UIDVALIDITY changed; select the test message again")
        row = client.fetch([ref.uid], ["FLAGS"]).get(ref.uid)
        if row is None:
            raise MailError("Test message no longer exists")
        return {v.decode("ascii", "replace") if isinstance(v, bytes) else str(v) for v in row.get(b"FLAGS", ())}


def main():
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description="Local read-only mailbox diagnostics; no secrets or message bodies are printed")
    parser.add_argument("action", choices=["folders", "stars", "unread"])
    parser.add_argument("--account", default="personal")
    args = parser.parse_args()
    try:
        config = MailConfig.load()
        service = MailService(config)
        account = service.account(args.account)
        if not os.getenv(account.username_env):
            os.environ[account.username_env] = getpass.getpass("Mailbox address (hidden): ")
        if not os.getenv(account.password_env):
            os.environ[account.password_env] = getpass.getpass("Mailbox password (hidden): ")
        if args.action == "folders":
            # Explicit admin-only inventory, before configuring the remote folder allowlist.
            with service.connection(account) as client:
                names = [name for fs, delimiter, name in client.list_folders()]
            print(json.dumps({"folder_names": names}, ensure_ascii=False, indent=2))
            return

        mid = input("Paste the test message ID returned by search_messages: ").strip()
        ref = MessageRef.decode(mid)
        if ref.account != account.id:
            raise MailError("Test message is from a different account")
        if args.action == "unread":
            before = flags_only(service, ref)
            if "\\Seen" in before:
                raise MailError("Choose an unread message for this test")
            result = service.read(mid)
            after = flags_only(service, ref)
            passed = before == after and "\\Seen" not in after and result["flags_unchanged"]
            print(json.dumps({"test": "unread_preserved", "passed": passed}))
            if not passed:
                raise SystemExit(1)
            return

        input("In Airmail, remove this test message's star, let it sync, then press Enter: ")
        before = flags_only(service, ref)
        input("In Airmail, star that same message, let it sync, then press Enter: ")
        starred = flags_only(service, ref)
        input("In Airmail, remove its star again, let it sync, then press Enter: ")
        after = flags_only(service, ref)
        passed = "\\Flagged" not in before and "\\Flagged" in starred and "\\Flagged" not in after
        print(json.dumps({"test": "airmail_standard_flag", "passed": passed,
                          "flagged_before": "\\Flagged" in before,
                          "flagged_starred": "\\Flagged" in starred,
                          "flagged_after": "\\Flagged" in after}))
        print("Restore the test message's original star state in Airmail.")
        if passed:
            print("You may now set airmail_flag_verified=true for this account and restart the service.")
        else:
            print("Keep airmail_flag_verified=false. Check sync or select another message and repeat.")
            raise SystemExit(1)
    except (MailError, ValueError, KeyError, OSError):
        print("Diagnostic could not complete; check local configuration, secrets and the selected message.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
