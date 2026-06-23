from email.message import Message
import importlib.util
from importlib import metadata
import json
from pathlib import Path
import sys

import pytest


def _load_install_guard():
    module_path = Path(__file__).resolve().parents[1] / "telegram_mcp" / "install_guard.py"
    spec = importlib.util.spec_from_file_location("test_install_guard_module", module_path)
    assert spec is not None and spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


install_guard = _load_install_guard()


def _direct_url(url: str, *, vcs: str | None = None) -> str:
    data = {"url": url}
    if vcs:
        data["vcs_info"] = {"vcs": vcs}
    return json.dumps(data)


def _identity(**overrides):
    values = {
        "name": "telegram-mcp",
        "version": "test-version",
        "authors": ("chigwell, l1v0n1",),
        "maintainers": (),
        "urls": ("Homepage, https://github.com/chigwell/telegram-mcp",),
        "summary": "Telegram integration for Claude via the Model Context Protocol",
        "direct_url": _direct_url("https://github.com/chigwell/telegram-mcp.git", vcs="git"),
    }
    values.update(overrides)
    return install_guard.DistributionIdentity(**values)


def test_install_guard_accepts_explicit_git_install():
    assert install_guard._looks_like_explicit_source_install(_identity()) is True


def test_install_guard_accepts_git_install_from_fork():
    identity = _identity(
        authors=("Fork Maintainer",),
        urls=("Homepage, https://github.com/example/telegram-mcp",),
        direct_url=_direct_url("https://github.com/example/telegram-mcp.git", vcs="git"),
    )

    assert install_guard._looks_like_explicit_source_install(identity) is True


def test_install_guard_accepts_file_install_from_project_root(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "telegram-mcp"\n',
        encoding="utf-8",
    )
    identity = _identity(direct_url=_direct_url(tmp_path.as_uri()))

    assert install_guard._looks_like_explicit_source_install(identity) is True


def test_install_guard_rejects_known_pypi_collision_metadata():
    identity = _identity(
        version="0.6.3",
        authors=("Furkan Kucuk <furkankucuk.dev@gmail.com>",),
        maintainers=("furkankucuk",),
        urls=("Project-URL, https://github.com/iamkucuk/telegram-mcp",),
        summary="MCP server for Telegram - lets AI agents communicate with users via Telegram",
        direct_url="",
    )

    assert install_guard._looks_like_explicit_source_install(identity) is False

    message = install_guard._format_unsafe_installation_message(identity)
    assert "Refusing to start" in message
    assert "0.6.3" in message
    assert "Furkan Kucuk" in message
    assert "git+https://github.com/chigwell/telegram-mcp.git" in message


def test_install_guard_rejects_spoofed_metadata_without_trusted_origin():
    identity = _identity(direct_url="")

    assert install_guard._looks_like_explicit_source_install(identity) is False


def test_install_guard_allows_source_checkout_without_distribution(monkeypatch):
    def empty_distributions():
        return iter(())

    monkeypatch.setattr(install_guard.metadata, "distributions", empty_distributions)

    install_guard.assert_safe_distribution()


def test_install_guard_allows_uv_editable_source_checkout_without_direct_url(
    monkeypatch, tmp_path
):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "telegram-mcp"\n',
        encoding="utf-8",
    )
    (tmp_path / "telegram_mcp.egg-info").mkdir()

    class FakeDistribution:
        version = "source-version"

        def __init__(self):
            self._path = tmp_path / "telegram_mcp.egg-info"
            self.files = []
            self.metadata = Message()
            self.metadata["Name"] = "telegram-mcp"
            self.metadata["Version"] = "source-version"
            self.metadata["Author"] = "chigwell, l1v0n1"
            self.metadata["Project-URL"] = "Homepage, https://github.com/chigwell/telegram-mcp"

        def read_text(self, _filename):
            return None

    monkeypatch.setattr(
        install_guard.metadata,
        "distributions",
        lambda: [FakeDistribution()],
    )

    install_guard.assert_safe_distribution()


def test_install_guard_raises_for_untrusted_installed_distribution(monkeypatch):
    class FakeDistribution:
        version = "0.6.3"

        def __init__(self):
            self.metadata = Message()
            self.metadata["Name"] = "telegram-mcp"
            self.metadata["Version"] = "0.6.3"
            self.metadata["Author"] = "Furkan Kucuk <furkankucuk.dev@gmail.com>"
            self.metadata["Project-URL"] = "Homepage, https://example.com/unrelated"

        def read_text(self, _filename):
            return None

    monkeypatch.setattr(
        install_guard.metadata,
        "distributions",
        lambda: [FakeDistribution()],
    )

    with pytest.raises(install_guard.UnsafeInstallationError, match="Refusing to start"):
        install_guard.assert_safe_distribution()


def test_install_guard_allows_fork_distribution_with_direct_url(monkeypatch):
    class FakeDistribution:
        version = "fork-version"

        def __init__(self):
            self.metadata = Message()
            self.metadata["Name"] = "telegram-mcp"
            self.metadata["Version"] = "fork-version"
            self.metadata["Author"] = "Fork Maintainer"
            self.metadata["Project-URL"] = "Homepage, https://github.com/example/telegram-mcp"

        def read_text(self, filename):
            if filename != "direct_url.json":
                return None
            return _direct_url("https://github.com/example/telegram-mcp.git", vcs="git")

    monkeypatch.setattr(
        install_guard.metadata,
        "distributions",
        lambda: [FakeDistribution()],
    )

    install_guard.assert_safe_distribution()


def _fake_distribution_from_identity(identity):
    class FakeDistribution:
        version = identity.version

        def __init__(self):
            self.metadata = Message()
            self.metadata["Name"] = identity.name
            self.metadata["Version"] = identity.version
            if identity.authors:
                self.metadata["Author"] = identity.authors[0]
            for url in identity.urls:
                self.metadata["Project-URL"] = url
            self.files = []
            self._path = None

        def read_text(self, filename):
            if filename != "direct_url.json":
                return None
            return identity.direct_url or None

    return FakeDistribution


def test_assert_safe_distribution_accepts_single_valid_distribution(monkeypatch):
    identity = _identity()
    monkeypatch.setattr(
        install_guard.metadata,
        "distributions",
        lambda: [_fake_distribution_from_identity(identity)()],
    )

    install_guard.assert_safe_distribution()


def test_assert_safe_distribution_accepts_when_any_duplicate_is_valid(monkeypatch, tmp_path):
    invalid = _identity(
        version="0.6.3",
        authors=("Furkan Kucuk <furkankucuk.dev@gmail.com>",),
        direct_url="",
    )
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "telegram-mcp"\n', encoding="utf-8")

    class ValidEggDistribution:
        version = "source-version"

        def __init__(self):
            self._path = tmp_path / "telegram_mcp.egg-info"
            self.files = []
            self.metadata = Message()
            self.metadata["Name"] = "telegram-mcp"
            self.metadata["Version"] = "source-version"

        def read_text(self, _filename):
            return None

    monkeypatch.setattr(
        install_guard.metadata,
        "distributions",
        lambda: [_fake_distribution_from_identity(invalid)(), ValidEggDistribution()],
    )

    install_guard.assert_safe_distribution()


def test_assert_safe_distribution_rejects_when_all_duplicates_invalid(monkeypatch):
    invalid_one = _identity(version="0.6.3", direct_url="")
    invalid_two = _identity(version="9.9.9", direct_url="")

    monkeypatch.setattr(
        install_guard.metadata,
        "distributions",
        lambda: [
            _fake_distribution_from_identity(invalid_one)(),
            _fake_distribution_from_identity(invalid_two)(),
        ],
    )

    with pytest.raises(install_guard.UnsafeInstallationError, match="Refusing to start"):
        install_guard.assert_safe_distribution()
