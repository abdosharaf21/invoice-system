"""Minimal local SMTP sink for Phase 15 UAT email delivery tests.

Speaks just enough SMTP (EHLO/HELO, MAIL FROM, RCPT TO, DATA, QUIT, RSET,
NOOP) to accept a message from Python's ``smtplib`` and capture it in memory
so the test can assert the message that the application actually sent.

Local, in-process test tooling only — it never talks to any external host.
"""

import socketserver
import threading
from email.parser import Parser


class _Handler(socketserver.StreamRequestHandler):
    messages = []  # type: list

    COMMANDS = ("EHLO", "HELO", "MAIL", "RCPT", "DATA", "QUIT", "RSET", "NOOP")

    def handle(self):
        self.received = []
        self.wfile.write(b"220 mock EINV UAT SMTP ready\r\n")
        self.wfile.flush()
        while True:
            try:
                line = self.rfile.readline()
            except Exception:
                return
            if not line:
                return
            cmd = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not cmd:
                continue
            verb = cmd.split(" ", 1)[0].upper()
            if verb == "EHLO" or verb == "HELO":
                self.wfile.write(b"250-mock EINV\r\n250 OK\r\n")
            elif verb == "MAIL":
                self.wfile.write(b"250 OK\r\n")
            elif verb == "RCPT":
                self.wfile.write(b"250 OK\r\n")
            elif verb == "DATA":
                self.wfile.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                self.wfile.flush()
                data_lines = []
                while True:
                    try:
                        dline = self.rfile.readline()
                    except Exception:
                        return
                    if not dline:
                        return
                    if dline == b".\r\n" or dline == b".\n":
                        break
                    data_lines.append(dline)
                raw = b"".join(data_lines).decode("utf-8", errors="replace")
                msg = Parser().parsestr(raw)
                _Handler.messages.append({
                    "from": msg.get("From"),
                    "to": msg.get("To"),
                    "subject": msg.get("Subject"),
                    "x_request_id": msg.get("X-Request-Id"),
                    "raw": raw,
                })
                self.wfile.write(b"250 OK queued\r\n")
            elif verb == "QUIT":
                self.wfile.write(b"221 Bye\r\n")
                self.wfile.flush()
                return
            elif verb in ("RSET", "NOOP"):
                self.wfile.write(b"250 OK\r\n")
            else:
                self.wfile.write(b"500 Unsupported command\r\n")
            self.wfile.flush()


class MockSMTP:
    """Context manager running a thread-local SMTP sink on a local port."""

    def __init__(self, port: int = 2525):
        self.port = port
        self._server = None
        self._thread = None

    def __enter__(self) -> "MockSMTP":
        _Handler.messages = []
        self._server = socketserver.ThreadingTCPServer(
            ("127.0.0.1", self.port), _Handler
        )
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        return False

    @property
    def messages(self):
        return list(_Handler.messages)