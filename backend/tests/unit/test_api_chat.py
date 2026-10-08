import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

import reviewerfinder.api.app as app_module
from reviewerfinder.api.app import app
from reviewerfinder.api.deps import get_chatbot_agent


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeAgent:
    def __init__(self):
        self.calls = []

    def invoke(self, payload, config):
        self.calls.append((payload, config))
        user_text = payload["messages"][-1]["content"]
        return {"messages": [FakeMessage(f"echo: {user_text}")]}


@pytest.fixture
def fake_agent():
    return FakeAgent()


@pytest.fixture
def client(fake_agent):
    app.dependency_overrides[get_chatbot_agent] = lambda: fake_agent
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_first_message_without_session_id_mints_one(client, fake_agent):
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "echo: hello"
    assert body["session_id"]  # a UUID was minted


def test_second_message_with_session_id_reuses_same_thread(client, fake_agent):
    first = client.post("/api/chat", json={"message": "my name is Jane"}).json()
    session_id = first["session_id"]

    second = client.post("/api/chat", json={"session_id": session_id, "message": "what is my name?"})
    assert second.status_code == 200

    assert len(fake_agent.calls) == 2
    assert fake_agent.calls[0][1]["configurable"]["thread_id"] == session_id
    assert fake_agent.calls[1][1]["configurable"]["thread_id"] == session_id


def test_chat_unavailable_returns_503_when_no_agent():
    app.dependency_overrides.pop(get_chatbot_agent, None)
    with TestClient(app) as test_client:
        test_client.app.state.chat_agent = None
        resp = test_client.post("/api/chat", json={"message": "hello"})
        assert resp.status_code == 503
    app.dependency_overrides.clear()


def test_chat_returns_503_when_chatbot_packages_missing(monkeypatch):
    monkeypatch.setattr(app_module, "build_chatbot", None)
    app.dependency_overrides.pop(get_chatbot_agent, None)
    with TestClient(app) as test_client:
        resp = test_client.post("/api/chat", json={"message": "hello"})
        assert resp.status_code == 503
        assert "chatbot packages are not installed" in resp.json()["detail"]
    app.dependency_overrides.clear()


def test_api_imports_without_chatbot_packages():
    """The keyless demo installs only `.[api]`, without LangChain/LangGraph.
    Simulate that in a fresh interpreter: the API module must still import,
    with chat switched off, rather than failing at startup.
    """
    code = (
        "import sys\n"
        "for name in ('langchain', 'langchain_ollama', 'langgraph'):\n"
        "    sys.modules[name] = None\n"
        "import reviewerfinder.api.app as app_module\n"
        "assert app_module.build_chatbot is None\n"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    subprocess.run([sys.executable, "-c", code], check=True, env=env)
