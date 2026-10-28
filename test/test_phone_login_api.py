"""Phone sign-in over HTTP: what it grants, what it refuses, and what it never reveals."""

import pytest
from flask import Blueprint, Flask, jsonify

from blueprints import phone_login
from database import phone_login_db as store
from limiter import limiter
from services.phone import sender

PHONE = "+919876543210"
OTHER = "+919123456789"
USER = "phone_api_user"


class FakeUser:
    def __init__(self, totp=False):
        self._totp = totp

    def is_totp_required_for(self, scope):
        return self._totp


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    store.init_db()
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setenv("PHONE_OTP_PROVIDER", "console")
    sent = []
    monkeypatch.setattr(sender, "send", lambda phone, code: sent.append((phone, code)))
    phone_login._codes.clear()
    phone_login._sends.clear()
    store.clear_phone(USER)
    store.db_session.remove()
    from blueprints import auth
    from database import auth_db, user_db

    monkeypatch.setattr(auth, "_try_resume_broker_session", lambda username: None)
    monkeypatch.setattr(user_db, "find_user_by_exact_username", lambda u: FakeUser())
    monkeypatch.setattr(auth_db, "log_login_attempt", lambda *a, **k: None)
    yield sent
    store.clear_phone(USER)
    store.db_session.remove()


@pytest.fixture
def app():
    application = Flask(__name__)
    application.config.update(TESTING=True, SECRET_KEY="phone-tests", PROPAGATE_EXCEPTIONS=True)
    application.register_blueprint(phone_login.phone_bp)
    auth = Blueprint("auth", __name__)
    auth.add_url_rule("/auth/login", "login", lambda: ("login", 200))
    application.register_blueprint(auth)
    application.add_url_rule(
        "/whoami", "whoami", lambda: jsonify(dict(__import__("flask").session))
    )
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _register():
    store.set_phone(USER, PHONE)
    store.db_session.remove()


def test_signing_in_with_the_registered_phone(client, stubs):
    _register()
    assert client.post("/auth/phone/request", json={"phone": "98765 43210"}).status_code == 200
    ((phone, code),) = stubs
    assert phone == PHONE
    response = client.post("/auth/phone/verify", json={"phone": PHONE, "code": code})
    assert response.status_code == 200 and response.get_json()["status"] == "success"
    assert client.get("/whoami").get_json()["user"] == USER


def test_answer_is_identical_for_registered_and_unregistered_numbers(client, stubs):
    _register()
    known = client.post("/auth/phone/request", json={"phone": PHONE})
    unknown = client.post("/auth/phone/request", json={"phone": OTHER})
    assert known.status_code == unknown.status_code == 200
    assert known.get_json() == unknown.get_json()
    assert [p for p, _ in stubs] == [PHONE]  # nothing is texted to a stranger


def test_throttle_is_identical_too(client):
    _register()
    for number in (PHONE, OTHER):
        client.post("/auth/phone/request", json={"phone": number})
        again = client.post("/auth/phone/request", json={"phone": number})
        assert again.status_code == 429


def test_a_valid_code_for_an_unregistered_number_signs_nobody_in(client):
    code = phone_login._book.issue("login", OTHER).code
    response = client.post("/auth/phone/verify", json={"phone": OTHER, "code": code})
    assert response.status_code == 401
    assert "user" not in client.get("/whoami").get_json()


def test_wrong_code_is_refused_and_five_burn_the_real_one(client, stubs):
    _register()
    client.post("/auth/phone/request", json={"phone": PHONE})
    code = stubs[0][1]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert (
            client.post("/auth/phone/verify", json={"phone": PHONE, "code": wrong}).status_code
            == 401
        )
    assert client.post("/auth/phone/verify", json={"phone": PHONE, "code": code}).status_code == 401
    assert "user" not in client.get("/whoami").get_json()


def test_second_factor_is_still_asked_for(client, stubs, monkeypatch):
    from database import user_db

    monkeypatch.setattr(user_db, "find_user_by_exact_username", lambda u: FakeUser(totp=True))
    _register()
    client.post("/auth/phone/request", json={"phone": PHONE})
    response = client.post("/auth/phone/verify", json={"phone": PHONE, "code": stubs[0][1]})
    assert response.get_json()["status"] == "totp_required"
    state = client.get("/whoami").get_json()
    assert "user" not in state and state["pending_totp_user"] == USER


def test_off_until_a_provider_is_chosen(client, monkeypatch):
    monkeypatch.delenv("PHONE_OTP_PROVIDER")
    assert client.get("/auth/phone/status").get_json()["enabled"] is False
    response = client.post("/auth/phone/request", json={"phone": PHONE})
    assert response.status_code == 400 and "not set up" in response.get_json()["message"]


def test_bad_number_is_explained_in_plain_words(client):
    response = client.post("/auth/phone/request", json={"phone": "12"})
    assert response.status_code == 400 and "mobile number" in response.get_json()["message"]


def test_registering_needs_a_signed_in_session(client):
    assert client.post("/auth/phone/register/request", json={"phone": PHONE}).status_code in (
        302,
        401,
    )


def test_registering_a_number_from_a_signed_in_session(client, stubs):
    from utils import session as session_utils

    with client.session_transaction() as s:
        s["user"], s["logged_in"] = USER, True
    original = session_utils.is_session_valid
    session_utils.is_session_valid = lambda: True
    try:
        assert (
            client.post("/auth/phone/register/request", json={"phone": "9876543210"}).status_code
            == 200
        )
        code = stubs[0][1]
        assert (
            client.post(
                "/auth/phone/register/verify", json={"phone": PHONE, "code": "x"}
            ).status_code
            == 400
        )
        done = client.post("/auth/phone/register/verify", json={"phone": PHONE, "code": code})
        assert done.status_code == 200 and done.get_json()["phone"] == "+91********10"
        assert client.get("/auth/phone/me").get_json()["phone"] == "+91********10"
    finally:
        session_utils.is_session_valid = original
    assert store.get_phone(USER) == PHONE
