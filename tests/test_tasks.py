import pytest


def test_list_tasks_empty(client):
    response = client.get("/tasks/")
    assert response.status_code == 200
    assert response.json() == []


def test_create_task(client):
    payload = {"title": "Fix CI pipeline", "description": "Investigate flaky tests", "status": "pending"}
    response = client.post("/tasks/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Fix CI pipeline"
    assert data["status"] == "pending"
    assert "id" in data


def test_create_task_minimal(client):
    response = client.post("/tasks/", json={"title": "Quick task"})
    assert response.status_code == 201
    assert response.json()["title"] == "Quick task"


def test_create_task_empty_title_fails(client):
    response = client.post("/tasks/", json={"title": ""})
    assert response.status_code == 422


def test_get_task(client):
    created = client.post("/tasks/", json={"title": "Deploy to prod"}).json()
    response = client.get(f"/tasks/{created['id']}")
    assert response.status_code == 200
    assert response.json()["title"] == "Deploy to prod"


def test_get_task_not_found(client):
    response = client.get("/tasks/99999")
    assert response.status_code == 404


def test_update_task_status(client):
    created = client.post("/tasks/", json={"title": "Review PR"}).json()
    response = client.put(f"/tasks/{created['id']}", json={"status": "done"})
    assert response.status_code == 200
    assert response.json()["status"] == "done"


def test_update_task_title(client):
    created = client.post("/tasks/", json={"title": "Old title"}).json()
    response = client.put(f"/tasks/{created['id']}", json={"title": "New title"})
    assert response.status_code == 200
    assert response.json()["title"] == "New title"


def test_delete_task(client):
    created = client.post("/tasks/", json={"title": "To be deleted"}).json()
    response = client.delete(f"/tasks/{created['id']}")
    assert response.status_code == 204
    assert client.get(f"/tasks/{created['id']}").status_code == 404


def test_delete_task_not_found(client):
    response = client.delete("/tasks/99999")
    assert response.status_code == 404


def test_list_tasks_after_create(client):
    client.post("/tasks/", json={"title": "Task A"})
    client.post("/tasks/", json={"title": "Task B"})
    response = client.get("/tasks/")
    assert response.status_code == 200
    assert len(response.json()) == 2
