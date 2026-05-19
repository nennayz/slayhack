from __future__ import annotations

from knowledge.settings import KnowledgeSettings


def test_defaults(tmp_path):
    s = KnowledgeSettings(root=tmp_path)
    assert s.vault_knowledge_dir == tmp_path / "vault" / "08 Knowledge"
    assert s.db_path == tmp_path / "knowledge.db"
    assert 0.0 < s.soft_threshold < s.strong_threshold <= 1.0
    assert s.embed_model == "text-embedding-3-small"


def test_thresholds_override_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_STRONG_THRESHOLD", "0.9")
    monkeypatch.setenv("KNOWLEDGE_SOFT_THRESHOLD", "0.7")
    s = KnowledgeSettings.from_env(root=tmp_path)
    assert s.strong_threshold == 0.9
    assert s.soft_threshold == 0.7
