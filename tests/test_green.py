import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/name/'launch.py')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
mail=module('household_mail')
tunnel=module('openai_mail_tunnel')

@pytest.fixture
def options():
    return dict(mailbox_username='synthetic@example.invalid',mailbox_password='SECRET-$-unicode-é',folders=['INBOX'],resource_url='https://mail.example.invalid/mcp',oauth_issuer='https://auth.example.invalid/',oauth_jwks_url='https://auth.example.invalid/keys',allowed_subjects=['owner'],allowed_client_ids=['client'],mail_app_hostname='abcd1234-household-mail')

def test_mapping_keeps_secrets_out_of_file(options):
    cfg, env=mail.prepare(options)
    assert options['mailbox_password'] not in cfg.model_dump_json()
    assert options['mailbox_username'] not in cfg.model_dump_json()
    assert env['IMAP_PERSONAL_PASSWORD']==options['mailbox_password']
    assert cfg.accounts[0].folders==['INBOX']
    assert not cfg.accounts[0].airmail_flag_verified

@pytest.mark.parametrize('change',[{'mailbox_password':''},{'folders':[]},{'folders':['INBOX\r\nSTORE']},{'allowed_subjects':[]},{'allowed_subjects':['owner other']},{'resource_url':'http://mail.invalid/mcp'},{'host':'evil.invalid'}])
def test_bad_mail_settings(options, change):
    options.update(change)
    with pytest.raises(ValueError): mail.prepare(options)

@pytest.mark.parametrize('host',['supervisor','homeassistant','localhost','127.0.0.1','evil.example.com','abcd1234-household-mail/path','abcd1234-household-mail:8123'])
def test_tunnel_not_general_proxy(host):
    with pytest.raises(ValueError):
        tunnel.prepare(dict(tunnel_id='tunnel_'+'a'*32,runtime_key='sk-synthetic',mail_app_hostname=host))

def test_tunnel_narrow_target():
    env=tunnel.prepare(dict(tunnel_id='tunnel_'+'a'*32,runtime_key='sk-synthetic',mail_app_hostname='abcd1234-household-mail'))
    assert env['MCP_SERVER_URL']=='http://abcd1234-household-mail:8000/mcp'
    assert env['HEALTH_LISTEN_ADDR']=='127.0.0.1:8080'

@pytest.mark.parametrize('mod',[mail,tunnel])
def test_startup_error_redacted(mod,capsys):
    with patch.object(Path,'read_text',side_effect=ValueError('SECRET')):
        with pytest.raises(SystemExit): mod.main()
    out=capsys.readouterr()
    assert 'SECRET' not in out.err+out.out
    assert 'Startup refused' in out.err

@pytest.mark.parametrize('name',['household_mail','openai_mail_tunnel'])
def test_no_host_or_home_privileges(name):
    cfg=json.loads((ROOT/name/'config.json').read_text())
    assert not cfg['host_network'] and not cfg['hassio_api'] and not cfg['homeassistant_api']
    assert not cfg.get('ports') and not cfg.get('map') and not cfg.get('privileged')
    assert cfg['apparmor'] and cfg['boot']=='manual'

def test_internal_host_auth_still_required(monkeypatch,options):
    from household_imap.server import build_server, make_app
    from household_imap.config import AuthConfig
    from starlette.testclient import TestClient
    cfg, env=mail.prepare(options)
    auth=AuthConfig(resource=options['resource_url'],issuer=options['oauth_issuer'],jwks_url=options['oauth_jwks_url'],allowed_subjects=['owner'],allowed_client_ids=['client'])
    monkeypatch.setenv('IMAP_INTERNAL_HOST','abcd1234-household-mail')
    with TestClient(make_app(build_server(cfg,auth),auth),base_url='http://abcd1234-household-mail:8000') as client:
        assert client.post('/mcp',json={}).status_code==401
    monkeypatch.setenv('IMAP_INTERNAL_HOST','*.example.com')
    with pytest.raises(ValueError): make_app(build_server(cfg,auth),auth)


def test_second_account_preserves_personal_and_secrets(options):
    before, old_env = mail.prepare(options)
    options.update(mum_enabled=True, mum_username='mum@example.invalid',
                   mum_password='synthetic-second-secret', mum_folders=['INBOX'])
    after, env = mail.prepare(options)
    assert after.accounts[0] == before.accounts[0]
    assert all(env[k] == v for k, v in old_env.items())
    mum = after.accounts[1]
    assert mum.id == 'mum' and mum.label == 'Mum – Combell'
    assert mum.host == 'imap.mailprotect.be' and mum.port == 993
    assert mum.folders == ['INBOX'] and mum.discover_sent
    assert env['IMAP_MUM_PASSWORD'] == options['mum_password']
    assert options['mum_password'] not in after.model_dump_json()
    assert options['mum_username'] not in after.model_dump_json()


def test_disabled_second_account_has_no_effect(options):
    before = mail.prepare(options)
    options.update(mum_enabled=False, mum_username='', mum_password='', mum_folders=['INBOX'])
    assert mail.prepare(options) == before


@pytest.mark.parametrize('change', [dict(mum_password=''), dict(mum_username=''),
    dict(mum_folders=[]), dict(mum_folders=['INBOX\r\nSTORE']), dict(mum_enabled='true')])
def test_bad_second_account_settings(options, change):
    options.update(mum_enabled=True, mum_username='mum@example.invalid',
                   mum_password='synthetic-second-secret', mum_folders=['INBOX'])
    options.update(change)
    with pytest.raises(ValueError):
        mail.prepare(options)
