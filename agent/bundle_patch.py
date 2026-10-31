"""Re-apply the AV1 crop to the installed selkies web bundle (agent start).

AMD VCN 4 VA-API pads the coded AV1 frame (width to x64, some heights by 2) and
Chromium ignores the render size, so text looks squeezed. Each decoded frame is
cropped to the configured size via VideoFrame visibleRect. Upstream:
selkies-project/selkies#496. Lost on every selkies reinstall, hence this.
"""
import glob
import importlib.util
import os
import tempfile
from pathlib import Path

_WORKER_FN = """// A driver may code a larger picture than the stream's (radeonsi pads AV1 to its
// alignment) and the decoder does not crop to the render size, so the frame is
// cropped to the configured size here; visibleRect cropping copies nothing.
function fitDecoded(f) {
  const c = decConfig;
  if (!c || (f.displayWidth === c.codedWidth && f.displayHeight === c.codedHeight)
      || f.codedWidth < c.codedWidth || f.codedHeight < c.codedHeight) return f;
  try {
    const g = new VideoFrame(f, { visibleRect: { x: 0, y: 0, width: c.codedWidth, height: c.codedHeight } });
    if (fitDecoded.logged !== f.displayWidth + 'x' + f.displayHeight) { fitDecoded.logged = f.displayWidth + 'x' + f.displayHeight; console.info('[Selkies] cropped decoded ' + fitDecoded.logged + ' to ' + g.displayWidth + 'x' + g.displayHeight); }
    f.close();
    return g;
  } catch (_) { return f; }
}

"""
_PAGE_FN = ("function __styxFit(s,w,h,f){if(!(f.displayWidth===w&&f.displayHeight===h)"
            "&&f.codedWidth>=w&&f.codedHeight>=h)try{let g=new VideoFrame(f,{visibleRect:"
            "{x:0,y:0,width:w,height:h}});f.close();f=g}catch(e){}return Bs(s,f)}")
_CONF = "function configureDecoder("
_QA = "function Qa(){"
_PRESENT = "present(f, statsOpen ? arrivalOf(f.timestamp) : NaN);"

# (name, marker, before, after)
PATCHES = [
    ("worker-fn", "function fitDecoded(f)", _CONF, _WORKER_FN + _CONF),
    ("worker-call", "present(fitDecoded(f)", _PRESENT,
     _PRESENT.replace("present(f,", "present(fitDecoded(f),")),
    ("page-fn", "function __styxFit(", _QA, _PAGE_FN + _QA),
    ("page-call", "output:__styxFit.bind", "output:Bs.bind(null,s)",
     "output:__styxFit.bind(null,s,l,u)"),
]


def patch_text(text: str) -> tuple[str, list[str], list[str]]:
    """-> (new_text, applied, skipped). Idempotent; never raises. All or
    nothing: a patch whose marker is present is already done; the rest apply
    only if every anchor matches exactly once (else text is returned unchanged
    and the unmatched names are `skipped`: another selkies version)."""
    todo = [p for p in PATCHES if p[1] not in text]
    skipped = [p[0] for p in todo if text.count(p[2]) != 1]
    if skipped:
        return text, [], skipped
    for _, _, before, after in todo:
        text = text.replace(before, after)
    return text, [p[0] for p in todo], []


def _bundles() -> list[str]:
    """selkies-core bundles of the selkies importable by this interpreter."""
    spec = importlib.util.find_spec("selkies")
    if spec is None or not spec.submodule_search_locations:
        return []
    return [f for d in spec.submodule_search_locations
            for f in glob.glob(os.path.join(d, "selkies_web/assets/selkies-core-*.js"))]


def apply(install_dir=None, log=print) -> None:
    """Patch the selkies-core bundle of the installed selkies. Never raises."""
    try:
        files = _bundles()
        if not files:
            log("bundle patch: no selkies web bundle found")
        for f in files:
            text = Path(f).read_text(encoding="utf-8")
            new, applied, skipped = patch_text(text)
            if skipped:
                log(f"bundle patch: unknown bundle {Path(f).name}, skipped")
                continue
            if not applied:
                log(f"bundle patch: already present in {Path(f).name}")
                continue
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(f), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(new)
                os.chmod(tmp, os.stat(f).st_mode & 0o7777)
                os.replace(tmp, f)
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
            log(f"bundle patch: applied {', '.join(applied)} to {Path(f).name}")
    except (OSError, ValueError, ImportError) as e:
        log(f"bundle patch failed: {e}")
