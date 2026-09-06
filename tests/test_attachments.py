"""
Tests for attachment listing and download, including filename safety.
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from officeclaw import policy
from officeclaw.exceptions import AttachmentNotAllowedError, AttachmentSecurityError

FILE_ATTACHMENT = {
    "@odata.type": "#microsoft.graph.fileAttachment",
    "id": "att-1",
    "name": "report.pdf",
    "contentType": "application/pdf",
    "size": 1024,
    "isInline": False,
}


@pytest.fixture(autouse=True)
def _no_block_logging(tmp_path):
    with (
        patch.object(policy, "LOG_DIR", tmp_path / "logs"),
        patch.object(policy, "BLOCK_LOG", tmp_path / "logs" / "email-blocked.log"),
        patch.object(policy, "ALERT_FILE", tmp_path / "logs" / "email-alert.json"),
    ):
        yield


DOWNLOAD_ENABLED = {"OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD": "true"}


@pytest.fixture
def client():
    """MailClient whose Graph client serves attachment metadata by id."""
    with patch("officeclaw.mail.GraphClient") as mock_class:
        from officeclaw.mail import MailClient

        graph = MagicMock()

        def get(endpoint, **kwargs):
            # download_attachment re-reads the attachment it is about to write.
            for attachment in graph.get_all.return_value:
                if endpoint.endswith(f"/attachments/{attachment['id']}"):
                    return attachment
            return {}

        graph.get.side_effect = get
        mock_class.return_value = graph
        yield MailClient(), graph


class TestDownload:
    def test_writes_file_from_inline_content_bytes(self, client, tmp_path):
        mc, graph = client
        graph.get_all.return_value = [
            {**FILE_ATTACHMENT, "contentBytes": base64.b64encode(b"hello").decode()}
        ]

        with patch.dict("os.environ", DOWNLOAD_ENABLED, clear=True):
            results = mc.download_attachments("msg-1", tmp_path)

        assert (tmp_path / "report.pdf").read_bytes() == b"hello"
        assert results[0]["path"].endswith("report.pdf")
        graph.get_binary.assert_not_called()

    def test_falls_back_to_value_endpoint(self, client, tmp_path):
        mc, graph = client
        graph.get_all.return_value = [FILE_ATTACHMENT]
        graph.get_binary.return_value = b"big file"

        with patch.dict("os.environ", DOWNLOAD_ENABLED, clear=True):
            mc.download_attachments("msg-1", tmp_path)

        assert (tmp_path / "report.pdf").read_bytes() == b"big file"
        assert graph.get_binary.call_args[0][0].endswith("/attachments/att-1/$value")

    def test_traversal_in_attachment_name_cannot_escape(self, client, tmp_path):
        mc, graph = client
        dest = tmp_path / "downloads"
        graph.get_all.return_value = [
            {
                **FILE_ATTACHMENT,
                "name": "../../.ssh/authorized_keys",
                "contentBytes": base64.b64encode(b"key").decode(),
            }
        ]

        with patch.dict("os.environ", DOWNLOAD_ENABLED, clear=True):
            results = mc.download_attachments("msg-1", dest)

        assert (dest / "authorized_keys").read_bytes() == b"key"
        assert not (tmp_path.parent / ".ssh").exists()
        assert results[0]["path"].startswith(str(dest))

    def test_existing_file_is_not_overwritten(self, client, tmp_path):
        mc, graph = client
        (tmp_path / "report.pdf").write_bytes(b"original")
        graph.get_all.return_value = [
            {**FILE_ATTACHMENT, "contentBytes": base64.b64encode(b"new").decode()}
        ]

        with patch.dict("os.environ", DOWNLOAD_ENABLED, clear=True):
            mc.download_attachments("msg-1", tmp_path)

        assert (tmp_path / "report.pdf").read_bytes() == b"original"
        assert (tmp_path / "report (1).pdf").read_bytes() == b"new"

    def test_non_file_attachments_are_saved_as_metadata(self, client, tmp_path):
        """An item or reference attachment has no bytes; its metadata is kept."""
        mc, graph = client
        graph.get_all.return_value = [
            {
                "@odata.type": "#microsoft.graph.itemAttachment",
                "id": "att-2",
                "name": "Forwarded mail",
            }
        ]

        dest = tmp_path / "dest"

        with patch.dict("os.environ", DOWNLOAD_ENABLED, clear=True):
            results = mc.download_attachments("msg-1", dest)

        written = list(dest.iterdir())
        assert [p.name for p in written] == ["Forwarded mail.json"]
        assert results[0]["path"].endswith(".json")
        assert "itemAttachment" in written[0].read_text()

    def test_inline_attachments_are_skipped_by_default(self, client, tmp_path):
        mc, graph = client
        graph.get_all.return_value = [
            {**FILE_ATTACHMENT, "isInline": True, "contentBytes": base64.b64encode(b"x").decode()}
        ]

        with patch.dict("os.environ", DOWNLOAD_ENABLED, clear=True):
            skipped = mc.download_attachments("msg-1", tmp_path)
            included = mc.download_attachments("msg-1", tmp_path, include_inline=True)

        assert skipped[0]["skipped"] == "inline"
        assert included[0]["path"]

    def test_destination_outside_allowlist_is_blocked(self, client, tmp_path):
        mc, graph = client
        wip = tmp_path / "wip"
        wip.mkdir()

        env = {**DOWNLOAD_ENABLED, "OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": str(wip)}
        with patch.dict("os.environ", env), pytest.raises(AttachmentNotAllowedError):
            mc.download_attachments("msg-1", tmp_path / "elsewhere")

        graph.get_all.assert_not_called()

    def test_destination_inside_allowlist_is_allowed(self, client, tmp_path):
        mc, graph = client
        wip = tmp_path / "wip"
        wip.mkdir()
        graph.get_all.return_value = [
            {**FILE_ATTACHMENT, "contentBytes": base64.b64encode(b"ok").decode()}
        ]

        env = {**DOWNLOAD_ENABLED, "OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": str(wip)}
        with patch.dict("os.environ", env):
            mc.download_attachments("msg-1", wip / "sub")

        assert (wip / "sub" / "report.pdf").read_bytes() == b"ok"


class TestDefaultDestination:
    """Where downloads go when --dest is not given."""

    def test_env_var_is_used_verbatim(self, tmp_path):
        target = tmp_path / "my downloads"
        with patch.dict("os.environ", {"OFFICECLAW_DOWNLOADS_DIR": str(target)}, clear=True):
            assert policy.default_download_dir() == target

    def test_env_var_expands_a_tilde(self):
        with patch.dict("os.environ", {"OFFICECLAW_DOWNLOADS_DIR": "~/attachments"}, clear=True):
            assert policy.default_download_dir() == Path.home() / "attachments"

    def test_the_1_0_5_variable_still_works(self, tmp_path):
        """An existing .env from 1.0.5 must not silently stop being honoured."""
        target = tmp_path / "old-downloads"
        env = {"OFFICECLAW_ATTACHMENT_DOWNLOAD_PATH": str(target)}

        with patch.dict("os.environ", env, clear=True), pytest.deprecated_call():
            assert policy.default_download_dir() == target

    def test_new_variable_wins_over_the_old_one(self, tmp_path):
        env = {
            "OFFICECLAW_DOWNLOADS_DIR": str(tmp_path / "new"),
            "OFFICECLAW_ATTACHMENT_DOWNLOAD_PATH": str(tmp_path / "old"),
        }
        with patch.dict("os.environ", env, clear=True):
            assert policy.default_download_dir() == tmp_path / "new"

    def test_falls_inside_the_allowlist_when_one_is_set(self, tmp_path):
        wip = tmp_path / "wip"
        other = tmp_path / "other"
        env = {"OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": f"{wip},{other}"}

        with patch.dict("os.environ", env, clear=True):
            assert policy.default_download_dir() == wip / "officeclaw_downloads"

    def test_platform_downloads_folder_otherwise(self, tmp_path):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(policy.platformdirs, "user_downloads_dir", return_value=str(tmp_path)),
        ):
            assert policy.default_download_dir() == tmp_path / "officeclaw_downloads"

    def test_default_destination_passes_its_own_allowlist_check(self, tmp_path):
        """The allowlist default must not be blocked by the allowlist."""
        wip = tmp_path / "wip"
        wip.mkdir()

        with patch.dict("os.environ", {"OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": str(wip)}):
            assert policy.check_download_dir(policy.default_download_dir())

    def test_download_uses_the_default_when_no_dest_given(self, client, tmp_path):
        mc, graph = client
        graph.get_all.return_value = [
            {**FILE_ATTACHMENT, "contentBytes": base64.b64encode(b"x").decode()}
        ]

        env = {**DOWNLOAD_ENABLED, "OFFICECLAW_DOWNLOADS_DIR": str(tmp_path / "dl")}
        with patch.dict("os.environ", env):
            results = mc.download_attachments("msg-1")

        assert (tmp_path / "dl" / "report.pdf").read_bytes() == b"x"
        assert results[0]["path"].startswith(str(tmp_path / "dl"))


class TestPortableFilenames:
    """Names are made safe for Windows as well as POSIX, on every platform."""

    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("report.pdf", "report.pdf"),
            ("../../.ssh/authorized_keys", "authorized_keys"),
            (r"..\..\Windows\System32\evil.exe", "evil.exe"),
            ('quote"and:pipe|.txt', "quoteandpipe.txt"),
            ("trailing dots...", "trailing dots"),
            ("trailing space ", "trailing space"),
            ("CON", "_CON"),
            ("nul.txt", "_nul.txt"),
            ("com1.log", "_com1.log"),
            ("", "attachment"),
            (None, "attachment"),
            ("...", "attachment"),
        ],
    )
    def test_names_are_reduced(self, given, expected):
        assert policy.safe_attachment_name(given) == expected

    def test_result_is_never_a_path(self):
        for name in ("/etc/passwd", r"C:\Windows\win.ini", "a/b/c.txt"):
            assert "/" not in policy.safe_attachment_name(name)
            assert "\\" not in policy.safe_attachment_name(name)


class TestDownloadGate:
    """Downloading is refused unless explicitly enabled."""

    def test_disabled_by_default(self, client, tmp_path):
        mc, graph = client
        graph.get_all.return_value = [FILE_ATTACHMENT]

        with patch.dict("os.environ", {}, clear=True), pytest.raises(AttachmentSecurityError):
            mc.download_attachments("msg-1", tmp_path)

        graph.get_all.assert_not_called()

    def test_size_limit_skips_rather_than_aborting(self, client, tmp_path):
        mc, graph = client
        graph.get_all.return_value = [
            {**FILE_ATTACHMENT, "size": 50 * 1024 * 1024, "contentBytes": ""}
        ]

        dest = tmp_path / "dest"
        env = {**DOWNLOAD_ENABLED, "OFFICECLAW_ATTACHMENT_MAX_SIZE_MB": "1"}
        with patch.dict("os.environ", env):
            results = mc.download_attachments("msg-1", dest)

        assert "exceeds maximum" in results[0]["skipped"]
        assert list(dest.iterdir()) == []
