from datetime import date
from types import SimpleNamespace
import pytest
from pydantic import ValidationError

from household_imap.mail import (MailService, MailError, Query, MessageRef, guard_commands,
                                 HEADER_ITEM, BODY_ITEM, parse_message, BODY_LIMIT)

RAW = b"From: Daenens <cleaner@example.invalid>\r\nTo: home@example.invalid\r\nSubject: Friday\r\nMessage-ID: <a@example.invalid>\r\n\r\nSee you Friday.\r\n"


class FakeIMAP:
    def __init__(self, *args, **kwargs):
        assert kwargs["ssl"] and kwargs["use_uid"]
        assert kwargs["ssl_context"].check_hostname
        self.calls = []
        self._imap = SimpleNamespace(_command=lambda *args: self.calls.append(args))
        self.flags = ()

    def login(self, username, password):
        self._imap._command("LOGIN", username, password)

    def logout(self):
        self._imap._command("LOGOUT")

    def select_folder(self, folder, readonly):
        assert readonly
        self.folder = folder
        self._imap._command("EXAMINE", folder)
        return {b"UIDVALIDITY": 99}

    def list_folders(self):
        self._imap._command("LIST", '""', '"*"')
        return [((), b"/", f) for f in ("INBOX", "Sent", "Private")]

    def search(self, criteria, charset):
        self._imap._command("UID", "SEARCH", "CHARSET", charset, str(criteria))
        return [1, 2, 3]

    def fetch(self, uids, items):
        self._imap._command("UID", "FETCH", ",".join(map(str, uids)), "(" + " ".join(items) + ")")
        return {uid: {b"FLAGS": self.flags, b"RFC822.SIZE": len(RAW), b"BODY[]<0>": RAW} for uid in uids}


def test_read_search_and_pagination(mail_config):
    clients = []
    def factory(*a, **kw):
        clients.append(FakeIMAP(*a, **kw))
        return clients[-1]
    service = MailService(mail_config, factory)
    first = service.search(Query(correspondent="Daenens"), limit=2)
    second = service.search(Query(), limit=2, offset=first["next_offset"])
    assert [m["uid"] for m in first["messages"]] == [3, 2]
    assert [(m["folder"], m["uid"]) for m in second["messages"]] == [("INBOX", 1), ("Sent", 3)]
    assert first["total_matches"] == 6
    read = service.read(first["messages"][0]["id"])
    assert read["flags_unchanged"] and read["flags_after"] == []
    assert "See you Friday" in read["text"]
    assert not read["raw_truncated"]
    commands = [call[0] for c in clients for call in c.calls]
    assert "EXAMINE" in commands and "SELECT" not in commands and "CLOSE" not in commands
    assert not any(c for c in commands if c in {"STORE", "EXPUNGE", "APPEND", "MOVE"})


@pytest.mark.parametrize("verb,args", [("SELECT", ["INBOX"]), ("CLOSE", []), ("EXPUNGE", []),
    ("APPEND", []), ("STORE", []), ("UID", ["STORE", "1", "+FLAGS", "\\Seen"]),
    ("UID", ["MOVE", "1", "Trash"]), ("UID", ["FETCH", "1", "(BODY[])"]),
    ("UID", ["FETCH", "1", "(RFC822)"]), ("UID", ["COPY", "1", "Trash"])])
def test_wire_guard_rejects_mutations(verb, args):
    fake = SimpleNamespace(_imap=SimpleNamespace(_command=lambda *args: pytest.fail("Sent unsafe command")))
    guard_commands(fake)
    with pytest.raises(MailError):
        fake._imap._command(verb, *args)


def test_visibility_and_stale_ids(mail_config):
    service = MailService(mail_config, FakeIMAP)
    assert [a["id"] for a in service.account_list()] == ["personal"]
    assert [f["name"] for f in service.list_folders("personal")["folders"]] == ["INBOX", "Sent"]
    for account, folder in [("hidden", "INBOX"), ("personal", "Private")]:
        ref = MessageRef(account=account, folder=folder, uidvalidity=99, uid=1).encode()
        with pytest.raises(MailError):
            service.read(ref)
    stale = MessageRef(account="personal", folder="INBOX", uidvalidity=1, uid=1).encode()
    with pytest.raises(MailError, match="stale"):
        service.read(stale)


@pytest.mark.parametrize("value", ["bad\r\nUID STORE 1 +FLAGS (\\Seen)", "\x00", "x" * 513])
def test_query_rejects_control_characters(value):
    with pytest.raises(ValidationError):
        Query(text=value)


def test_structured_filters():
    q = Query(sender="Alice", recipient="Bob", correspondent="Daenens", subject="huis", text="factuur",
              since=date(2026, 9, 1), before=date(2026, 9, 12), flagged=True)
    terms = q.criteria()
    assert "SINCE" in terms and "BEFORE" in terms and "FLAGGED" in terms
    assert ["FROM", "Daenens"] in terms
    with pytest.raises(ValidationError):
        Query(since=date(2026, 9, 2), before=date(2026, 9, 1))


def test_failure_is_partial_and_redacted(mail_config):
    class Broken(FakeIMAP):
        def select_folder(self, folder, readonly):
            if folder == "Sent":
                raise RuntimeError("fake-test-password private@example.invalid")
            return super().select_folder(folder, readonly)
    result = MailService(mail_config, Broken).search(Query())
    assert result["messages"] and result["errors"] and not result["complete"]
    assert result["next_offset"] is None
    assert "fake-test-password" not in str(result) and "private@example.invalid" not in str(result)


def test_html_and_mime():
    raw = b'Subject: =?utf-8?q?R=C3=A9union?=\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<head>hidden</head><p>Hello<img src="https://tracker.invalid/a"><script>bad()</script>world</p>'
    parsed = parse_message(raw, True)
    assert parsed["subject"] == "Réunion"
    assert "Hello" in parsed["text"] and "hidden" not in parsed["text"] and "bad()" not in parsed["text"]
    assert "tracker" not in parsed["text"]


def test_invalid_id_and_limits(mail_config):
    svc = MailService(mail_config, FakeIMAP)
    for mid in ["not an id", "x" * 2049]:
        with pytest.raises(MailError):
            svc.read(mid)
    for limit in [0, 51]:
        with pytest.raises(MailError):
            svc.search(Query(), limit=limit)
    with pytest.raises(MailError):
        svc.recent(0)


def test_thread_explicitly_best_effort(mail_config):
    service = MailService(mail_config, FakeIMAP)
    mid = service.search(Query(), limit=1)["messages"][0]["id"]
    result = service.thread(mid, limit=2)
    assert len(result["messages"]) == 2 and not result["complete"] and result["truncated"]


def test_body_cap_is_reported(mail_config):
    class Large(FakeIMAP):
        def fetch(self, uids, items):
            rows = super().fetch(uids, items)
            for row in rows.values():
                row[b"RFC822.SIZE"] = BODY_LIMIT * 2
            return rows
    svc = MailService(mail_config, Large)
    ref = MessageRef(account="personal", folder="INBOX", uidvalidity=99, uid=1).encode()
    assert svc.read(ref)["raw_truncated"]


def test_sent_discovery_does_not_expose_messages(mail_config):
    from household_imap.config import Account
    class SpecialFolders(FakeIMAP):
        def list_folders(self):
            return [((), b'/', 'INBOX'), ((b'\\Sent',), b'/', 'INBOX.Verzonden'),
                    ((), b'/', 'Sent')]
    personal = mail_config.accounts[0]
    mum = Account(id='mum', label='Mum', username_env='IMAP_USER',
                  password_env='IMAP_PASSWORD', enabled=True,
                  folders=['INBOX'], discover_sent=True)
    config = mail_config.model_copy(update={'accounts': [personal, mum]})
    service = MailService(config, SpecialFolders)
    result = service.list_folders('mum')
    assert result['server_sent_folders'] == ['INBOX.Verzonden']
    assert [f['name'] for f in result['folders']] == ['INBOX']
    assert 'server_sent_folders' not in service.list_folders('personal')
    with pytest.raises(MailError, match='not exposed'):
        service.targets(['mum'], ['INBOX.Verzonden'])
    read = service.read(service.search(Query(), ['mum'], limit=1)['messages'][0]['id'])
    assert read['account'] == 'mum' and read['flags_unchanged']


def test_header_search_checks_flags_without_fetching_body(mail_config):
    clients = []
    def factory(*a, **kw):
        client = FakeIMAP(*a, **kw)
        clients.append(client)
        return client
    result = MailService(mail_config, factory).recent(account_ids=['personal'],
                                                     folders=['INBOX'], limit=1)
    assert result['messages'][0]['flags_unchanged']
    assert 'text' not in result['messages'][0]
    calls = clients[0].calls
    assert not any(BODY_ITEM in str(c) for c in calls)
    assert sum(c[0:2] == ('UID', 'FETCH') for c in calls) == 3


def test_header_search_reports_concurrent_flag_change(mail_config):
    class Changing(FakeIMAP):
        def fetch(self, uids, items):
            rows = super().fetch(uids, items)
            if HEADER_ITEM in items:
                self.flags = (b'\\Seen',)
            return rows
    result = MailService(mail_config, Changing).search(Query(), ['personal'], ['INBOX'], limit=1)
    assert result['messages'][0]['flags_unchanged'] is False
