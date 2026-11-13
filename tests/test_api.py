def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_memory_lifecycle(client):
    created = client.post(
        "/api/v1/memory", json={"content": "I prefer concise answers", "category": "preference"}
    )
    assert created.status_code == 201
    memory_id = created.json()["id"]
    assert client.get("/api/v1/memory").json()[0]["content"] == "I prefer concise answers"
    assert client.delete(f"/api/v1/memory/{memory_id}").status_code == 204


def test_sensitive_task_requires_approval(client):
    task = client.post(
        "/api/v1/tasks",
        json={"title": "Draft a file", "action": "write_file", "risk_level": 2},
    )
    assert task.status_code == 201
    assert task.json()["status"] == "awaiting_approval"
    approvals = client.get("/api/v1/approvals").json()
    assert len(approvals) == 1
    assert approvals[0]["status"] == "pending"


def test_purchase_is_denied(client):
    response = client.post(
        "/api/v1/tasks", json={"title": "Buy item", "action": "purchase", "risk_level": 3}
    )
    assert response.status_code == 403


def test_conversation_history_and_delete(client, monkeypatch):
    async def local_reply(self, messages, memories):
        assert messages[-1]["content"] == "Remember this thread"
        return "Thread remembered locally"

    monkeypatch.setattr("backend.api.chat.OllamaClient.chat", local_reply)
    created = client.post("/api/v1/chat", json={"message": "Remember this thread"})
    assert created.status_code == 200
    conversation_id = created.json()["conversation_id"]

    listing = client.get("/api/v1/chat/conversations")
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == conversation_id

    detail = client.get(f"/api/v1/chat/conversations/{conversation_id}")
    assert [message["role"] for message in detail.json()["messages"]] == [
        "user",
        "assistant",
    ]
    assert client.delete(f"/api/v1/chat/conversations/{conversation_id}").status_code == 204
    assert client.get(f"/api/v1/chat/conversations/{conversation_id}").status_code == 404


def test_approval_decision_updates_task(client):
    task = client.post(
        "/api/v1/tasks",
        json={
            "title": "Save a draft",
            "action": "write_file",
            "risk_level": 2,
            "arguments": {"path": "notes/draft.txt", "content": "Local draft"},
        },
    ).json()
    approval = client.get("/api/v1/approvals").json()[0]
    decided = client.post(f"/api/v1/approvals/{approval['id']}/approved")
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"
    refreshed = client.get("/api/v1/tasks").json()
    assert next(item for item in refreshed if item["id"] == task["id"])["status"] == "completed"
    receipt = client.get(f"/api/v1/tasks/{task['id']}/receipts").json()[0]
    assert receipt["status"] == "completed"
    assert client.get("/api/v1/files/notes/draft.txt").json()["content"] == "Local draft"


def test_server_enforces_write_risk_even_when_client_claims_zero(client):
    response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Risk spoof",
            "action": "write_file",
            "risk_level": 0,
            "arguments": {"path": "unsafe.txt", "content": "must wait"},
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "awaiting_approval"
    assert client.get("/api/v1/files").json() == []


def test_workspace_rejects_path_traversal(client):
    task = client.post(
        "/api/v1/tasks",
        json={
            "title": "Traversal attempt",
            "action": "read_file",
            "risk_level": 1,
            "arguments": {"path": "../secret.txt"},
        },
    )
    assert task.status_code == 201
    assert task.json()["status"] == "failed"
    receipt = client.get(f"/api/v1/tasks/{task.json()['id']}/receipts").json()[0]
    assert "outside the authorized workspace" in receipt["result"]


def test_research_returns_local_synthesis_with_sources(client, monkeypatch):
    async def fake_collect(self, query, limit):
        assert query == "local AI"
        assert limit == 2
        return [
            {
                "title": "Artificial intelligence",
                "url": "https://example.test/ai",
                "excerpt": "AI systems perform tasks associated with intelligence.",
            }
        ]

    async def fake_chat(self, messages, memories):
        assert "SOURCE 1" in messages[0]["content"]
        assert memories == []
        return "Local AI report [Source 1]"

    monkeypatch.setattr("backend.api.research.WikipediaResearch.collect", fake_collect)
    monkeypatch.setattr("backend.api.research.OllamaClient.chat", fake_chat)
    response = client.post("/api/v1/research", json={"query": "local AI", "max_sources": 2})
    assert response.status_code == 200
    assert response.json()["report"] == "Local AI report [Source 1]"
    assert response.json()["sources"][0]["title"] == "Artificial intelligence"


def test_audit_log_records_memory_actions(client):
    client.post("/api/v1/memory", json={"content": "Audit this", "category": "test"})
    logs = client.get("/api/v1/audit").json()
    assert logs[0]["action"] == "memory.create"
    assert logs[0]["outcome"] == "success"


def test_automation_lifecycle(client):
    created = client.post(
        "/api/v1/automations",
        json={
            "title": "Inventory workspace",
            "action": "list_files",
            "interval_minutes": 30,
        },
    )
    assert created.status_code == 201
    automation_id = created.json()["id"]
    assert client.get("/api/v1/automations").json()[0]["enabled"] is True
    paused = client.post(f"/api/v1/automations/{automation_id}/enabled/false")
    assert paused.json()["enabled"] is False
    assert client.delete(f"/api/v1/automations/{automation_id}").status_code == 204


def test_optional_api_key_protects_data_routes(client):
    from backend.core.config import get_settings

    settings = get_settings()
    settings.api_key = "test-secret"
    try:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/memory").status_code == 401
        assert (
            client.get("/api/v1/memory", headers={"X-Assistant-Key": "test-secret"}).status_code
            == 200
        )
    finally:
        settings.api_key = None
