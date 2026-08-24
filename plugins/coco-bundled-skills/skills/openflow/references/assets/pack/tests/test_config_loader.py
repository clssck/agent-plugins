from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ASSETS = Path(__file__).resolve().parent.parent.parent
if str(ASSETS) not in sys.path:
    sys.path.insert(0, str(ASSETS))

from pack import config_loader


def test_expand_tokens_supports_connector_runtime_and_env(monkeypatch):
    monkeypatch.setenv("TENANT_SUFFIX", "blue")

    expanded = config_loader.expand_tokens(
        "${runtime}-${connector.name}-${connector.name|upper}-${connector.name|lower}-${env.TENANT_SUFFIX}",
        connector_name="Tenant_A",
        runtime="rt1",
    )

    assert expanded == "rt1-Tenant_A-TENANT_A-tenant_a-blue"


def test_expand_tokens_leaves_unknown_tokens_untouched():
    assert config_loader.expand_tokens(
        "before-${unknown.token}-after",
        connector_name="c1",
        runtime="rt1",
    ) == "before-${unknown.token}-after"


def test_is_secret_ref_matches_supported_schemes_only():
    assert config_loader.is_secret_ref("<pg-password>")
    assert config_loader.is_secret_ref("snowflake:DB.SCHEMA.SECRET")
    assert not config_loader.is_secret_ref("vault:kv/openflow/password")
    assert not config_loader.is_secret_ref("env:OPENFLOW_PASSWORD")
    assert not config_loader.is_secret_ref("not-a-secret")
    assert not config_loader.is_secret_ref(123)


def test_fingerprint_is_deterministic_and_value_free():
    fp = config_loader.fingerprint("secret-value")

    assert fp == {
        "length": len(b"secret-value"),
        "sha256": hashlib.sha256(b"secret-value").hexdigest(),
    }
    assert "secret-value" not in repr(fp)


def test_load_json(tmp_path):
    json_path = tmp_path / "config.json"
    json_path.write_text(
        '{"runtime":"rt2","connector_type":"mysql","shared":{"snowflake":{},"source":{}},"connectors":[{"name":"c2","tables_regex":".*"}]}',
        encoding="utf-8",
    )

    json_cfg = config_loader.load(json_path)

    assert json_cfg.runtime == "rt2"
    assert json_cfg.connectors[0].tables_regex == ".*"


def test_load_yaml_when_pyyaml_is_available(tmp_path):
    pytest.importorskip("yaml")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
runtime: rt1
connector_type: postgresql
shared:
  snowflake: {role: OPENFLOW_ROLE}
  source: {password: <pg-password>}
connectors:
  - name: c1
    tables: [public.users]
""",
        encoding="utf-8",
    )

    yaml_cfg = config_loader.load(yaml_path)

    assert yaml_cfg.runtime == "rt1"
    assert yaml_cfg.connectors[0].tables == ["public.users"]


def test_load_malformed_json_raises_clear_value_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON config"):
        config_loader.load(path)


def test_load_malformed_yaml_raises_clear_value_error(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "bad.yaml"
    path.write_text("runtime: [unterminated", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid YAML config"):
        config_loader.load(path)


def test_load_rejects_non_mapping_root(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="Config root must be a mapping"):
        config_loader.load(path)