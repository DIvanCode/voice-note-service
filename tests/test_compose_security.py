"""Assert the one-shot migration remains disabled and tightly sandboxed."""
from pathlib import Path

import yaml


def test_existing_whisper_cache_has_opt_in_least_privilege_migration():
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    bot = services["bot"]
    migrate = services["whisper-cache-migrate"]

    assert migrate["profiles"] == ["maintenance"]
    assert migrate["network_mode"] == "none"
    assert migrate["user"] == "0:0"
    assert migrate["cap_drop"] == ["ALL"]
    assert migrate["cap_add"] == ["CHOWN"]
    assert migrate["read_only"] is True
    assert "no-new-privileges:true" in migrate["security_opt"]
    assert migrate["volumes"] == ["whisper_cache:/cache"]
    assert migrate["entrypoint"] == ["chown", "-R", "10001:10001", "/cache"]
    assert "environment" not in migrate
    assert migrate["restart"] == "no"

    assert bot["cap_drop"] == ["ALL"]
    assert "whisper_cache:/cache" in bot["volumes"]
    assert "whisper-cache-migrate" not in (bot.get("depends_on") or {})
    assert "whisper-cache-migrate" not in (services["llama"].get("depends_on") or {})
