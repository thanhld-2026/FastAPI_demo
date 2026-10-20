"""Mục 5: Quản lý tag (chỉ Admin)."""

from app import crud


def test_create_tag_race_condition_returns_409(client, make_user, monkeypatch):
    admin = make_user("boss", admin=True)
    client.post("/api/v1/tags", json={"name": "backend"}, headers=admin["headers"])
    # Giả lập 2 request tạo cùng tên: request sau cũng qua được bước check trước
    monkeypatch.setattr(crud.tag, "get_by_name", lambda db, name: None)

    resp = client.post("/api/v1/tags", json={"name": "backend"}, headers=admin["headers"])

    assert resp.status_code == 409


def test_delete_unknown_tag_returns_404(client, make_user):
    admin = make_user("boss", admin=True)

    assert client.delete("/api/v1/tags/999", headers=admin["headers"]).status_code == 404
