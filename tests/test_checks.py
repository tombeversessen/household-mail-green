import json
import pytest
from pydantic import ValidationError
from household_imap import check
from household_imap.config import MailConfig, AuthConfig
from household_imap.mail import MailService, Query, MessageRef
from test_mail import FakeIMAP


def test_empty_success_is_not_failure(mail_config):
    class Empty(FakeIMAP):
        def search(self, criteria, charset):
            return []
    result = MailService(mail_config, Empty).search(Query())
    assert result["messages"] == [] and result["complete"] and result["errors"] == []


def test_config_fails_closed(mail_config, auth_config):
    data = mail_config.model_dump()
    data["accounts"][0]["enabled"] = False
    with pytest.raises(ValidationError):
        MailConfig.model_validate(data)
    data = mail_config.model_dump()
    data["accounts"][0]["folders"] = []
    with pytest.raises(ValidationError):
        MailConfig.model_validate(data)
    for field, value in [("resource", "http://mail.example.com/mcp"), ("allowed_subjects", []), ("allowed_client_ids", [])]:
        with pytest.raises(ValidationError):
            AuthConfig.model_validate({**auth_config.model_dump(), field: value})


@pytest.mark.parametrize("stages,passed", [([set(), {"\\Flagged"}, set()], True),
                                         ([set(), set(), set()], False),
                                         ([{"\\Flagged"}, {"\\Flagged"}, set()], False)])
def test_star_diagnostic_requires_transition(monkeypatch, capsys, mail_config, stages, passed):
    mid = MessageRef(account="personal", folder="INBOX", uidvalidity=99, uid=1).encode()
    answers = iter([mid, "", "", ""])
    samples = iter(stages)
    monkeypatch.setattr(check.MailConfig, "load", lambda: mail_config)
    monkeypatch.setattr(check, "flags_only", lambda *args: next(samples))
    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    monkeypatch.setattr("sys.argv", ["imap-check", "stars"])
    monkeypatch.setattr(check.logging, "disable", lambda *args: None)
    if passed:
        check.main()
    else:
        with pytest.raises(SystemExit) as exc:
            check.main()
        assert exc.value.code == 1
    output = capsys.readouterr().out
    assert json.loads(output.splitlines()[0])["passed"] is passed
    assert "fake-test-password" not in output
