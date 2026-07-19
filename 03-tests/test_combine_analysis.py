import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import combine_analysis


def test_main_exits_early_without_gap_csv(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(combine_analysis.config, "CLIPS_DIR", str(tmp_path))
    combine_analysis.main()
    assert "No gap analysis CSV found" in capsys.readouterr().out


def test_main_exits_early_without_reflection_csv(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(combine_analysis.config, "CLIPS_DIR", str(tmp_path))
    (tmp_path / "analysis_2026-01-01_00-00-00.csv").write_text("clip,duration_sec,gap_T5000\n")
    combine_analysis.main()
    assert "No reflection analysis CSV found" in capsys.readouterr().out


def test_main_handles_empty_datasets(tmp_path, monkeypatch, capsys):
    """Both CSVs present but contain no data rows — must not raise IndexError."""
    monkeypatch.setattr(combine_analysis.config, "CLIPS_DIR", str(tmp_path))
    (tmp_path / "analysis_2026-01-01_00-00-00.csv").write_text("clip,duration_sec,gap_T5000\n")
    (tmp_path / "reflection_analysis_2026-01-01_00-00-00.csv").write_text(
        "clip,reflection_pct,verdict\n"
    )
    combine_analysis.main()
    assert "No clips matched" in capsys.readouterr().out