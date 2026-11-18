"""Project screenshots (ADR-0022, step 4.2a): upload checks and re-encoding,
caption, delete, reorder, files removed with their rows."""

import struct
import zlib
from io import BytesIO

import pytest
from PIL import ExifTags, Image

from app.media import images
from app.projects import screenshots
from app.settings import settings
from tests.conftest import login, make_github_transport

PROJECTS = "/api/v1/projects"
GPS_IFD = ExifTags.IFD.GPSInfo
ORIENTATION = ExifTags.Base.Orientation


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_root", tmp_path)
    return tmp_path


@pytest.fixture
def client(auth_client):
    login(auth_client)
    return auth_client


@pytest.fixture
def other_client(client, make_auth_client):
    other = make_auth_client(make_github_transport(github_user_id=20002, github_login="other"))
    login(other)
    return other


@pytest.fixture
def project(client) -> dict:
    resp = client.post(PROJECTS, json={"title": "Shop"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _image(size=(40, 20), mode="RGB", fmt="PNG", color="red", **save) -> bytes:
    out = BytesIO()
    Image.new(mode, size, color).save(out, fmt, **save)
    return out.getvalue()


def _bomb_png(width: int, height: int) -> bytes:
    """A PNG whose header claims a huge image; its pixels are never decoded."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body)
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b""))
        + chunk(b"IEND", b"")
    )


def _upload(client, project, data: bytes, name="shot.png", **form):
    return client.post(
        f"{PROJECTS}/{project['id']}/screenshots",
        files={"file": (name, data, "image/png")},
        data=form,
    )


def _items(resp, status=200) -> list[dict]:
    assert resp.status_code == status, resp.text
    return resp.json()["items"]


def _file_error(resp) -> str:
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    [field] = error["details"]["fields"]
    assert field["loc"] == ["body", "file"]
    return field["type"]


def _stored(media_root, item) -> Image.Image:
    return Image.open(media_root / item["url"].removeprefix("/media/"))


def _files(media_root) -> list:
    return [p for p in media_root.rglob("*") if p.is_file()]


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


class TestUpload:
    @pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
    def test_accepted_formats_are_stored_as_webp(self, client, project, media_root, fmt):
        [item] = _items(_upload(client, project, _image(fmt=fmt)), 201)
        assert set(item) == {"id", "url", "caption", "width", "height"}
        assert item["url"].startswith(f"/media/projects/{project['id']}/")
        assert item["url"].endswith(".webp")
        assert (item["width"], item["height"]) == (40, 20)
        stored = _stored(media_root, item)
        assert stored.format == "WEBP"
        assert stored.size == (40, 20)

    def test_screenshots_are_in_the_project_response(self, client, project):
        assert project["screenshots"] == []
        [item] = _items(_upload(client, project, _image(), caption="Home"), 201)
        body = client.get(f"{PROJECTS}/{project['id']}").json()
        assert body["screenshots"] == [item]

    def test_long_side_is_reduced(self, client, project, media_root):
        [item] = _items(_upload(client, project, _image((3000, 1000))), 201)
        assert (item["width"], item["height"]) == (2560, 853)
        assert _stored(media_root, item).size == (2560, 853)

    def test_transparency_is_kept(self, client, project, media_root):
        [item] = _items(_upload(client, project, _image(mode="RGBA", color=(255, 0, 0, 128))), 201)
        assert _stored(media_root, item).mode == "RGBA"

    def test_exif_with_gps_is_dropped_and_orientation_applied(self, client, project, media_root):
        exif = Image.Exif()
        exif[ORIENTATION] = 6  # rotate 90° clockwise to display
        exif[GPS_IFD] = {1: "N", 2: (55.0, 45.0, 0.0)}
        data = _image((40, 20), fmt="JPEG", exif=exif)
        assert Image.open(BytesIO(data)).getexif().get_ifd(GPS_IFD)  # the input carries GPS

        [item] = _items(_upload(client, project, data), 201)
        assert (item["width"], item["height"]) == (20, 40)
        stored = _stored(media_root, item)
        assert len(stored.getexif()) == 0
        assert "exif" not in stored.info

    def test_text_with_image_name_is_rejected(self, client, project, media_root):
        resp = _upload(client, project, b"<svg onload=alert(1)>", name="shot.png")
        assert _file_error(resp) == "invalid_image"
        assert _files(media_root) == []

    def test_other_image_format_is_rejected(self, client, project):
        assert _file_error(_upload(client, project, _image(fmt="GIF"))) == "invalid_image"

    def test_truncated_image_is_rejected(self, client, project):
        data = _image((200, 200), fmt="JPEG")
        assert _file_error(_upload(client, project, data[: len(data) // 2])) == "invalid_image"

    # 49 Mpx is caught by our check, 900 Mpx already by Pillow's in open().
    @pytest.mark.parametrize("side", [7_000, 30_000])
    def test_decompression_bomb_is_rejected_from_its_header(self, client, project, side):
        assert _file_error(_upload(client, project, _bomb_png(side, side))) == "too_many_pixels"

    def test_file_over_five_megabytes_is_rejected(self, client, project):
        data = b"\0" * (images.MAX_UPLOAD_BYTES + 1)
        assert _file_error(_upload(client, project, data)) == "image_too_large"

    def test_missing_file_is_rejected(self, client, project):
        resp = client.post(f"{PROJECTS}/{project['id']}/screenshots", data={"caption": "x"})
        assert resp.status_code == 422
        assert resp.json()["error"]["details"]["fields"] == [
            {"loc": ["body", "file"], "type": "missing"}
        ]

    def test_caption_is_plain_text(self, client, project):
        [item] = _items(_upload(client, project, _image(), caption="  Checkout page  "), 201)
        assert item["caption"] == "Checkout page"
        assert _items(_upload(client, project, _image(), caption="   "), 201)[1]["caption"] is None

        resp = _upload(client, project, _image(), caption="x" * 201)
        assert resp.status_code == 422
        assert resp.json()["error"]["details"]["fields"] == [
            {"loc": ["body", "caption"], "type": "string_too_long"}
        ]

    def test_six_is_the_limit(self, client, project, media_root):
        for _ in range(6):
            _upload(client, project, _image())
        resp = _upload(client, project, _image())
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "SCREENSHOT_LIMIT_REACHED"
        assert resp.json()["error"]["details"] == {"limit": 6}
        assert len(_files(media_root)) == 6

    def test_file_is_removed_when_the_row_is_not_written(
        self, client, project, media_root, monkeypatch
    ):
        # Another upload took the last place between the early check and the locked one.
        calls = []

        def check_limit(db, project_id):
            calls.append(project_id)
            if len(calls) > 1:
                raise screenshots.limit_reached()

        monkeypatch.setattr(screenshots, "check_limit", check_limit)
        assert _upload(client, project, _image()).status_code == 409
        assert _files(media_root) == []

    def test_foreign_or_unknown_project_is_not_found(self, client, other_client, project):
        assert _upload(other_client, project, _image()).status_code == 404
        unknown = {"id": "00000000-0000-4000-8000-000000000000"}
        assert _upload(client, unknown, _image()).status_code == 404

    def test_origin_is_required(self, make_auth_client, project, client, media_root):
        # A multipart form is a "simple" cross-site request: only the Origin check stops it.
        bare = make_auth_client(send_origin=False)
        bare.cookies = client.cookies
        resp = _upload(bare, project, _image())
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "CSRF_ORIGIN_INVALID"
        assert _files(media_root) == []


# ---------------------------------------------------------------------------
# Caption, delete, order
# ---------------------------------------------------------------------------


def _three(client, project) -> list[dict]:
    for caption in ("a", "b", "c"):
        items = _items(_upload(client, project, _image(), caption=caption), 201)
    return items


class TestChanges:
    def test_caption_is_changed_and_cleared(self, client, project):
        first, *_ = _three(client, project)
        url = f"{PROJECTS}/{project['id']}/screenshots/{first['id']}"
        assert _items(client.patch(url, json={"caption": " New "}))[0]["caption"] == "New"
        assert _items(client.patch(url, json={"caption": None}))[0]["caption"] is None
        assert client.patch(url, json={}).status_code == 422
        assert client.patch(url, json={"caption": "x", "url": "/x"}).status_code == 422

    def test_screenshot_of_another_project_is_not_found(self, client, project):
        [item] = _items(_upload(client, project, _image()), 201)
        other = client.post(PROJECTS, json={}).json()
        for screenshot_id in (item["id"], "not-a-uuid"):
            url = f"{PROJECTS}/{other['id']}/screenshots/{screenshot_id}"
            assert client.patch(url, json={"caption": "x"}).status_code == 404
            assert client.delete(url).status_code == 404

    def test_foreign_user_cannot_change_them(self, client, other_client, project):
        [item] = _items(_upload(client, project, _image()), 201)
        url = f"{PROJECTS}/{project['id']}/screenshots/{item['id']}"
        assert other_client.patch(url, json={"caption": "x"}).status_code == 404
        assert other_client.delete(url).status_code == 404
        reorder = f"{PROJECTS}/{project['id']}/screenshots/reorder"
        assert other_client.post(reorder, json={"screenshot_ids": [item["id"]]}).status_code == 404

    def test_delete_removes_the_file_and_closes_the_gap(self, client, project, media_root):
        first, second, third = _three(client, project)
        url = f"{PROJECTS}/{project['id']}/screenshots/{second['id']}"
        items = _items(client.delete(url))
        assert [i["caption"] for i in items] == ["a", "c"]
        assert not (media_root / second["url"].removeprefix("/media/")).exists()
        # The positions are 1..2 again: a new upload goes last and fits.
        items = _items(_upload(client, project, _image(), caption="d"), 201)
        assert [i["caption"] for i in items] == ["a", "c", "d"]

    def test_last_delete_removes_the_project_directory(self, client, project, media_root):
        [item] = _items(_upload(client, project, _image()), 201)
        client.delete(f"{PROJECTS}/{project['id']}/screenshots/{item['id']}")
        assert not (media_root / "projects" / project["id"]).exists()

    def test_reorder(self, client, project):
        a, b, c = _three(client, project)
        url = f"{PROJECTS}/{project['id']}/screenshots/reorder"
        items = _items(client.post(url, json={"screenshot_ids": [c["id"], a["id"], b["id"]]}))
        assert [i["caption"] for i in items] == ["c", "a", "b"]
        body = client.get(f"{PROJECTS}/{project['id']}").json()
        assert [s["caption"] for s in body["screenshots"]] == ["c", "a", "b"]

    def test_reorder_needs_the_whole_current_set(self, client, project):
        a, b, _ = _three(client, project)
        url = f"{PROJECTS}/{project['id']}/screenshots/reorder"
        resp = client.post(url, json={"screenshot_ids": [b["id"], a["id"]]})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "SCREENSHOT_ORDER_MISMATCH"

        resp = client.post(url, json={"screenshot_ids": [a["id"], a["id"]]})
        assert resp.status_code == 422
        assert resp.json()["error"]["details"]["fields"][0]["type"] == "duplicate_screenshot"

    def test_project_delete_removes_its_files(self, client, project, media_root):
        _three(client, project)
        assert client.delete(f"{PROJECTS}/{project['id']}").status_code == 204
        assert _files(media_root) == []
        assert not (media_root / "projects" / project["id"]).exists()
