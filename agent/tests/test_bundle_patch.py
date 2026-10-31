import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bundle_patch as bp  # noqa: E402

PRISTINE = ("worker{function configureDecoder(c){}\n"
            "out(){ present(f, statsOpen ? arrivalOf(f.timestamp) : NaN); }}\n"
            "page{function Qa(){}} new VideoDecoder({output:Bs.bind(null,s),error:e})")
REAL = Path.home() / ".local/share/styx-agent/selkies-core-BGbb3Bx7.js.bak-av1crop"


def test_applies_to_pristine():
    new, applied, skipped = bp.patch_text(PRISTINE)
    assert applied == [p[0] for p in bp.PATCHES] and skipped == []
    assert "present(fitDecoded(f)," in new
    assert "output:__styxFit.bind(null,s,l,u)" in new
    assert new.index("function __styxFit") < new.index("function Qa(){")


def test_idempotent():
    once = bp.patch_text(PRISTINE)[0]
    again, applied, skipped = bp.patch_text(once)
    assert again == once and applied == [] and skipped == []


def test_unknown_bundle_unchanged():
    text = "something else entirely function Qa(){} function Qa(){}"
    new, applied, skipped = bp.patch_text(text)
    assert new == text and applied == [] and "worker-fn" in skipped
    assert "page-fn" in skipped  # anchor occurs twice


def test_partial_match_leaves_text_unchanged():
    # worker anchors present, page anchors missing -> nothing applied
    text = PRISTINE.replace("function Qa(){}", "")
    new, applied, skipped = bp.patch_text(text)
    assert new == text and applied == [] and "page-fn" in skipped


def test_partial_with_marker_present_applies_rest():
    half = bp.patch_text(PRISTINE)[0].replace("output:__styxFit.bind(null,s,l,u)",
                                              "output:Bs.bind(null,s)")
    new, applied, skipped = bp.patch_text(half)
    assert applied == ["page-call"] and skipped == []


def _tree(tmp_path, text):
    d = tmp_path / "selkies/selkies_web/assets"
    d.mkdir(parents=True)
    f = d / "selkies-core-abc123.js"
    f.write_text(text)
    f.chmod(0o640)
    return f


def _spec(tmp_path):
    return SimpleNamespace(submodule_search_locations=[str(tmp_path / "selkies")])


def _apply(tmp_path, logs, spec="tree"):
    s = _spec(tmp_path) if spec == "tree" else spec
    with patch.object(bp.importlib.util, "find_spec", return_value=s) as fs:
        bp.apply("/ignored", logs.append)
    fs.assert_called_once_with("selkies")


def test_apply_tree(tmp_path):
    f = _tree(tmp_path, PRISTINE)
    logs = []
    _apply(tmp_path, logs)
    assert "__styxFit" in f.read_text()
    assert os.stat(f).st_mode & 0o777 == 0o640
    assert logs[0].startswith("bundle patch: applied")
    assert [p for p in f.parent.iterdir()] == [f]
    logs.clear()
    _apply(tmp_path, logs)
    assert logs == ["bundle patch: already present in selkies-core-abc123.js"]


def test_apply_unknown_and_missing(tmp_path):
    logs = []
    _apply(tmp_path, logs, spec=None)
    assert logs == ["bundle patch: no selkies web bundle found"]
    f = _tree(tmp_path, "nope")
    logs.clear()
    _apply(tmp_path, logs)
    assert logs == ["bundle patch: unknown bundle selkies-core-abc123.js, skipped"]
    assert f.read_text() == "nope"


def test_apply_partial_file_untouched(tmp_path):
    text = PRISTINE.replace("function Qa(){}", "")
    f = _tree(tmp_path, text)
    _apply(tmp_path, [])
    assert f.read_text() == text


def test_apply_never_raises(tmp_path):
    f = _tree(tmp_path, PRISTINE)
    f.chmod(0)
    if os.access(f, os.R_OK):
        pytest.skip("root ignores modes")
    logs = []
    _apply(tmp_path, logs)
    assert "failed" in logs[0]


@pytest.fixture
def real_bundle(tmp_path):
    if not REAL.exists():
        pytest.skip("real pristine bundle absent")
    return _tree(tmp_path, REAL.read_text())


def test_real_pristine(real_bundle):
    new, applied, skipped = bp.patch_text(real_bundle.read_text())
    assert len(applied) == 4 and skipped == []
