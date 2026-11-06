"""Ad-hoc checks for the send path (Gmail service mocked). Run: .venv/bin/python -m tests.check_send"""
import base64
import shutil
import sys
from email import policy
from email import message_from_bytes
from unittest import mock

sys.path.insert(0, ".")

shutil.rmtree("data", ignore_errors=True)  # start from a clean slate

from app import main as m  # noqa: E402
from app import mailer  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# ---------- 1. raw message format accepted by the Gmail API ----------

class FakeRequest:
    def execute(self):
        return {"id": "m1"}


class FakeMessages:
    def __init__(self):
        self.captured = None

    def send(self, userId, body):
        self.captured = (userId, body)
        return FakeRequest()


class FakeUsers:
    def __init__(self, messages):
        self._messages = messages

    def messages(self):
        return self._messages


class FakeService:
    def __init__(self):
        self.messages = FakeMessages()

    def users(self):
        return FakeUsers(self.messages)


svc = FakeService()
mailer.send_email(svc, to_email="a@x.com", subject="Hi & welcome", html="<b>html</b>", text="plain text")
user_id, body = svc.messages.captured
assert user_id == "me", user_id
raw = base64.urlsafe_b64decode(body["raw"])
msg = message_from_bytes(raw, policy=policy.default)
assert msg["To"] == "a@x.com", msg["To"]
assert msg["Subject"] == "Hi & welcome", msg["Subject"]
assert msg.is_multipart(), "expected multipart/alternative"
kinds = [p.get_content_type() for p in msg.iter_parts()]
assert kinds == ["text/plain", "text/html"], kinds
print("raw message format ok")

# ---------- 2. send orchestration: per-recipient failure + retry ----------

sent = []
attempts = {"bad": 0}


def fake_send_email(service, to_email, subject, html, text):
    if to_email == "bad@x.com":
        attempts["bad"] += 1
        if attempts["bad"] == 1:
            raise RuntimeError("fake smtp failure: 550 recipient rejected")
    sent.append(to_email)


with mock.patch.object(mailer, "get_service", return_value=object()), \
     mock.patch.object(mailer, "send_email", side_effect=fake_send_email), \
     mock.patch.object(mailer, "token_exists", return_value=True), \
     mock.patch("time.sleep", return_value=None), \
     TestClient(m.app) as client:

    for name, email in [("A", "a@x.com"), ("B", "b@x.com"), ("C", "bad@x.com")]:
        r = client.post("/api/participants", json={"name": name, "email": email})
        assert r.status_code == 201, r.text

    r = client.post("/api/draw")
    assert r.status_code == 200, r.text

    # first batch: bad@x.com fails, the other two go out
    r = client.post("/api/send", json={})
    assert r.status_code == 200, r.text
    st = client.get("/api/state").json()
    statuses = list(st["send_status"].values())
    assert statuses.count("sent") == 2, st
    assert statuses.count("failed") == 1, st
    assert "sending" not in statuses, st
    failed_id = [k for k, v in st["send_status"].items() if v == "failed"][0]
    assert "550 recipient rejected" in st["send_errors"][failed_id], st["send_errors"]
    assert sorted(sent) == ["a@x.com", "b@x.com"], sent
    print("first batch ok (2 sent, 1 failed with recorded error)")

    # second batch: only the failed one is re-sent, and this time it succeeds
    sent.clear()
    r = client.post("/api/send", json={})
    assert r.status_code == 200, r.text
    assert r.json()["sent"] == 1, r.json()
    assert sent == ["bad@x.com"], sent
    st = client.get("/api/state").json()
    assert set(st["send_status"].values()) == {"sent"}, st
    assert st["send_errors"] == {}, st
    print("retry ok (only the failed recipient was re-sent)")

    # force: everyone gets a duplicate
    sent.clear()
    r = client.post("/api/send", json={"force": True})
    assert r.status_code == 200, r.text
    assert r.json()["sent"] == 3, r.json()
    assert len(sent) == 3, sent
    print("force re-send ok")

print("all send-path checks passed")
