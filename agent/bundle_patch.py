"""Re-apply the AV1 crop to the installed selkies web bundle (agent start).

AMD VCN 4 VA-API pads the coded AV1 frame (width to x64, some heights by 2) and
Chromium ignores the render size, so text looks squeezed. Each decoded frame is
cropped to the configured size via VideoFrame visibleRect. Upstream:
selkies-project/selkies#496. Lost on every selkies reinstall, hence this.
"""
import glob
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
    """-> (new_text, applied, skipped). Idempotent; never raises. A patch whose
    marker is present is already done; one whose anchor is not unique is
    skipped (other selkies version)."""
    applied, skipped = [], []
    for name, marker, before, after in PATCHES:
        if marker in text:
            continue
        if text.count(before) == 1:
            text = text.replace(before, after)
            applied.append(name)
        else:
            skipped.append(name)
    return text, applied, skipped


def apply(install_dir, log=print) -> None:
    """Patch every selkies-core bundle under <install>/venv. Never raises."""
    pat = str(Path(install_dir) / "venv/lib/python*/site-packages/selkies"
              "/selkies_web/assets/selkies-core-*.js")
    try:
        files = glob.glob(pat)
        if not files:
            log("bundle patch: no selkies web bundle found")
        for f in files:
            text = Path(f).read_text(encoding="utf-8")
            new, applied, skipped = patch_text(text)
            if skipped:
                log(f"bundle patch: unknown bundle {Path(f).name}, "
                    f"skipped {', '.join(skipped)}")
            if not applied:
                if not skipped:
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
    except (OSError, ValueError) as e:
        log(f"bundle patch failed: {e}")
