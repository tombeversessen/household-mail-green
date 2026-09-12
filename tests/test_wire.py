"""Use the real IMAPClient against a local TLS IMAP server, including MIME literals."""
import datetime
import ipaddress
import re
import socketserver
import ssl
import threading

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from imapclient import IMAPClient

from household_imap.mail import MailService, Query
from test_mail import RAW


def test_real_imapclient_tls_and_wire_commands(tmp_path, mail_config):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                            x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert_path, key_path)
    commands = []

    class Handler(socketserver.StreamRequestHandler):
        def setup(self):
            self.request = tls.wrap_socket(self.request, server_side=True)
            super().setup()

        def handle(self):
            self.wfile.write(b"* OK IMAP test\r\n")
            while line := self.rfile.readline():
                tag, command, *rest = line.rstrip(b"\r\n").split(b" ", 2)
                commands.append(command)
                args = rest[0] if rest else b""
                if command == b"CAPABILITY":
                    self.wfile.write(b"* CAPABILITY IMAP4rev1\r\n")
                elif command == b"LOGIN":
                    pass
                elif command == b"EXAMINE":
                    self.wfile.write(b"* 1 EXISTS\r\n* FLAGS (\\Seen \\Flagged)\r\n* OK [UIDVALIDITY 99] stable\r\n")
                elif command == b"LIST":
                    self.wfile.write(b'* LIST () "/" "INBOX"\r\n')
                elif command == b"UID" and args.startswith(b"SEARCH"):
                    commands.append(b"UID SEARCH")
                    self.wfile.write(b"* SEARCH 1\r\n")
                elif command == b"UID" and args.startswith(b"FETCH"):
                    commands.append(b"UID FETCH")
                    if b"BODY.PEEK" in args:
                        commands.append(b"BODY.PEEK")
                        section = b"HEADER.FIELDS (FROM TO CC SUBJECT DATE MESSAGE-ID REFERENCES IN-REPLY-TO)" if b"HEADER.FIELDS" in args else b""
                        self.wfile.write(b"* 1 FETCH (UID 1 FLAGS () RFC822.SIZE " + str(len(RAW)).encode()
                                         + b" BODY[" + section + b"]<0> {" + str(len(RAW)).encode() + b"}\r\n"
                                         + RAW + b")\r\n")
                    else:
                        self.wfile.write(b"* 1 FETCH (UID 1 FLAGS ())\r\n")
                elif command == b"LOGOUT":
                    self.wfile.write(b"* BYE done\r\n" + tag + b" OK logout\r\n")
                    return
                else:
                    self.wfile.write(tag + b" BAD forbidden\r\n")
                    continue
                self.wfile.write(tag + b" OK done\r\n")

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
    server = Server(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        def factory(*args, **kwargs):
            return IMAPClient("127.0.0.1", port=server.server_address[1], ssl=True,
                              ssl_context=ssl.create_default_context(cafile=str(cert_path)), use_uid=True, timeout=5)
        service = MailService(mail_config, factory)
        found = service.search(Query(correspondent="Daenens"), folders=["INBOX"])
        assert not found["errors"], found
        assert found["messages"][0]["subject"] == "Friday"
        read = service.read(found["messages"][0]["id"])
        assert read["flags_unchanged"] and "See you Friday" in read["text"]
        assert b"BODY.PEEK" in commands and b"EXAMINE" in commands
        assert set(commands) <= {b"CAPABILITY", b"LOGIN", b"EXAMINE", b"UID", b"UID SEARCH", b"UID FETCH", b"BODY.PEEK", b"LOGOUT"}
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
