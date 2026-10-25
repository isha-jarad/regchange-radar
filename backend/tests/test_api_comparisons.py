import uuid

import pytest

from app.core.config import settings
from tests.pdf_factory import make_blank_pdf_bytes, make_encrypted_pdf_bytes

ZERO_ID = "00000000-0000-0000-0000-000000000000"


def upload(client, old, new, *, old_name="old.pdf", new_name="new.pdf",
           old_label="v1", new_label="v2"):
    return client.post(
        "/comparisons",
        files={
            "old_file": (old_name, old, "application/pdf"),
            "new_file": (new_name, new, "application/pdf"),
        },
        data={"old_version_label": old_label, "new_version_label": new_label},
    )


def create(client, old, new, **kwargs) -> dict:
    response = upload(client, old, new, **kwargs)
    assert response.status_code == 201
    return response.json()


def review_url(comparison_id: str, change_id: int) -> str:
    return f"/comparisons/{comparison_id}/changes/{change_id}/review"


# ---- health ----------------------------------------------------------------

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "regchange-radar"}


def test_database_health(client):
    response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "database"}


# ---- create ----------------------------------------------------------------

def test_create_comparison_returns_expected_result(client, old_pdf, new_pdf):
    response = upload(client, old_pdf, new_pdf, old_name="policy_v1.pdf", new_name="policy_v2.pdf")
    assert response.status_code == 201
    body = response.json()

    uuid.UUID(body["id"])  # raises if the id is not a valid UUID
    assert (body["old_filename"], body["new_filename"]) == ("policy_v1.pdf", "policy_v2.pdf")
    assert (body["old_version_label"], body["new_version_label"]) == ("v1", "v2")
    assert len(body["old_sha256"]) == 64
    assert (body["old_paragraph_count"], body["new_paragraph_count"]) == (11, 12)
    assert (
        body["unchanged_count"],
        body["inserted_count"],
        body["deleted_count"],
        body["replaced_count"],
    ) == (6, 1, 1, 4)
    assert (body["high_count"], body["medium_count"], body["low_count"]) == (4, 0, 1)
    assert body["ruleset_version"] == "2026.1"
    assert body["total_changes"] == 6
    assert body["pending_review_count"] == 6
    assert [c["priority"] for c in body["changes"]] == [
        "none", "high", "high", "low", "high", "high",
    ]
    assert [f["rule_id"] for f in body["changes"][1]["flags"]] == [
        "OBLIGATION_LANGUAGE", "PERMISSION_LANGUAGE", "NUMERIC_VALUE",
    ]


def test_rejects_non_pdf_extension(client, new_pdf):
    response = upload(client, b"hello", new_pdf, old_name="notes.txt")
    assert response.status_code == 415
    assert response.json() == {"detail": "Old file: Only .pdf files are accepted."}


def test_rejects_pdf_name_with_other_content(client, new_pdf):
    response = upload(client, b"hello world", new_pdf, old_name="fake.pdf")
    assert response.status_code == 415
    assert response.json() == {"detail": "Old file: The file content is not a valid PDF."}


def test_rejects_empty_file(client, new_pdf):
    response = upload(client, b"", new_pdf)
    assert response.status_code == 400
    assert response.json() == {"detail": "Old file: The uploaded file is empty."}


def test_error_message_names_the_new_file_when_it_is_the_problem(client, old_pdf):
    response = upload(client, old_pdf, b"hello", new_name="notes.txt")
    assert response.status_code == 415
    assert response.json()["detail"].startswith("New file:")


@pytest.mark.parametrize(
    ("bad_pdf", "expected_detail"),
    [
        (b"%PDF-1.7 this is not really a pdf",
         "Old file: The PDF could not be read. It may be corrupted."),
        (make_blank_pdf_bytes(),
         "Old file: No extractable text was found. Scanned PDFs are not supported."),
        (make_encrypted_pdf_bytes(), "Old file: The PDF is password-protected."),
    ],
    ids=["corrupt", "no-text", "encrypted"],
)
def test_rejects_unreadable_pdfs(client, new_pdf, bad_pdf, expected_detail):
    response = upload(client, bad_pdf, new_pdf)
    assert response.status_code == 400
    assert response.json() == {"detail": expected_detail}
    assert "Traceback" not in response.text  # no internals leak to the client


def test_rejects_oversized_file(client, old_pdf, new_pdf, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)
    response = upload(client, old_pdf, new_pdf)
    assert response.status_code == 413
    assert response.json() == {"detail": "Old file: The file exceeds the maximum allowed size."}


@pytest.mark.parametrize(
    "labels",
    [
        {},
        {"old_version_label": "v1"},
        {"old_version_label": "   ", "new_version_label": "v2"},
    ],
    ids=["missing", "one-missing", "blank"],
)
def test_requires_non_blank_version_labels(client, old_pdf, new_pdf, labels):
    response = client.post(
        "/comparisons",
        files={
            "old_file": ("old.pdf", old_pdf, "application/pdf"),
            "new_file": ("new.pdf", new_pdf, "application/pdf"),
        },
        data=labels,
    )
    assert response.status_code == 422


# ---- list ------------------------------------------------------------------

def test_list_is_empty_before_any_comparison(client):
    response = client.get("/comparisons")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_list_is_newest_first_and_supports_paging(client, old_pdf, new_pdf):
    create(client, old_pdf, new_pdf, new_label="first")
    create(client, old_pdf, new_pdf, new_label="second")

    def page(query: str):
        body = client.get(f"/comparisons{query}").json()
        return [item["new_version_label"] for item in body["items"]], body["total"]

    assert page("") == (["second", "first"], 2)
    assert page("?limit=1") == (["second"], 2)
    assert page("?limit=1&offset=1") == (["first"], 2)
    assert page("?offset=5") == ([], 2)

    first_item = client.get("/comparisons").json()["items"][0]
    assert "changes" not in first_item  # the list shows summaries only


@pytest.mark.parametrize("query", ["?limit=0", "?limit=101", "?offset=-1", "?limit=abc"])
def test_list_rejects_invalid_paging(client, query):
    assert client.get(f"/comparisons{query}").status_code == 422


# ---- get one ---------------------------------------------------------------

def test_get_returns_the_saved_comparison(client, old_pdf, new_pdf):
    created = create(client, old_pdf, new_pdf)
    response = client.get(f"/comparisons/{created['id']}")
    assert response.status_code == 200
    fetched = response.json()
    assert fetched["id"] == created["id"]
    assert fetched["changes"] == created["changes"]
    assert fetched["total_changes"] == 6


def test_get_unknown_comparison_returns_404(client):
    response = client.get(f"/comparisons/{ZERO_ID}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Comparison not found"}


def test_get_malformed_id_returns_422(client):
    assert client.get("/comparisons/not-a-uuid").status_code == 422


# ---- review ----------------------------------------------------------------

def test_review_updates_status_and_note(client, old_pdf, new_pdf):
    created = create(client, old_pdf, new_pdf)
    change_id = created["changes"][1]["id"]

    response = client.patch(
        review_url(created["id"], change_id),
        json={"review_status": "reviewed", "review_note": "Checked against the source."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "reviewed"
    assert body["review_note"] == "Checked against the source."
    assert body["reviewed_at"] is not None
    assert len(body["flags"]) == 3

    fetched = client.get(f"/comparisons/{created['id']}").json()
    assert fetched["pending_review_count"] == 5


def test_note_is_kept_unless_included_in_the_request(client, old_pdf, new_pdf):
    created = create(client, old_pdf, new_pdf)
    url = review_url(created["id"], created["changes"][1]["id"])

    client.patch(url, json={"review_status": "reviewed", "review_note": "Checked"})

    follow_up = client.patch(url, json={"review_status": "needs_follow_up"}).json()
    assert follow_up["review_status"] == "needs_follow_up"
    assert follow_up["review_note"] == "Checked"

    back_to_pending = client.patch(url, json={"review_status": "pending"}).json()
    assert back_to_pending["reviewed_at"] is None

    cleared = client.patch(url, json={"review_status": "reviewed", "review_note": None}).json()
    assert cleared["review_note"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"review_status": "done"},
        {},
        {"review_status": "reviewed", "typo_field": 1},
        {"review_status": "reviewed", "review_note": "x" * 2001},
    ],
    ids=["bad-status", "empty-body", "unknown-field", "note-too-long"],
)
def test_review_rejects_invalid_requests(client, old_pdf, new_pdf, payload):
    created = create(client, old_pdf, new_pdf)
    url = review_url(created["id"], created["changes"][0]["id"])
    assert client.patch(url, json=payload).status_code == 422


def test_review_unknown_change_returns_404(client, old_pdf, new_pdf):
    created = create(client, old_pdf, new_pdf)
    response = client.patch(
        review_url(created["id"], 999999), json={"review_status": "reviewed"}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Change not found"}


def test_a_change_cannot_be_reviewed_through_another_comparison(client, old_pdf, new_pdf):
    first = create(client, old_pdf, new_pdf, new_label="first")
    second = create(client, old_pdf, new_pdf, new_label="second")
    foreign_change_id = second["changes"][0]["id"]

    response = client.patch(
        review_url(first["id"], foreign_change_id), json={"review_status": "reviewed"}
    )
    assert response.status_code == 404