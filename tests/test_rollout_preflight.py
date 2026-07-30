def test_rollout_preflight_writes_evidence_without_secrets(full_app, tmp_path, monkeypatch):
    import app.services.rollout_preflight as preflight

    monkeypatch.setattr(
        preflight, "_command",
        lambda *args: (0, "abc123" if "rev-parse" in args else ""),
    )
    full_app.config["SKUNKBOX_SERVICE_SECRET"] = "never-print-this"
    full_app.config["SKUNKBOX_BASE_URL"] = "https://skunk.example"
    output = tmp_path / "evidence.md"

    result = full_app.test_cli_runner().invoke(args=[
        "tenant-rollout-preflight",
        "--environment", "test",
        "--output", str(output),
    ])

    assert result.exit_code == 0, result.output
    text = output.read_text()
    assert "Preflight Evidence (test)" in text
    assert "Human-controlled gates" in text
    assert "never-print-this" not in text
