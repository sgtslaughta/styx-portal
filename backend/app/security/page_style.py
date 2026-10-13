"""Shared look for the few pages the backend renders (spec §7 tokens)."""
import html

_CSS = """
@font-face{font-family:"Commissioner Variable";src:url(/_styx/app/assets/commissioner-wght.woff2) format("woff2");font-weight:100 900;font-display:swap}
:root{--bg:#EDF1EF;--fg:#0F1C22;--muted:#4A5A60;--link:#2A767C;--btn:#2A767C;--btn-fg:#EDF1EF}
@media (prefers-color-scheme:dark){:root{--bg:#0F1C22;--fg:#EDF1EF;--muted:#9FB0B4;--link:#6FB7BC;--btn:#6FB7BC;--btn-fg:#0F1C22}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:16px;
background:var(--bg);color:var(--fg);font:15px/1.55 "Commissioner Variable",system-ui,sans-serif}
main{max-width:34rem}h1{font-size:1.56rem;line-height:1.2;margin:0 0 .5rem;font-weight:600}
p{color:var(--muted)}a{color:var(--link)}button{font:inherit;background:var(--btn);color:var(--btn-fg);
border:0;border-radius:.5rem;padding:.6rem 1rem;cursor:pointer}code{font:13px ui-monospace,monospace}
.btn{display:inline-flex;align-items:center;min-height:44px;padding:0 1rem;border-radius:.5rem;background:var(--btn);
color:var(--btn-fg);font-weight:600;text-decoration:none}
.actions{display:flex;gap:.75rem;align-items:center;margin-top:1rem}
button:focus-visible,a:focus-visible{outline:2px solid var(--link);outline-offset:2px}
"""


def styx_page(title: str, body: str) -> str:
    """Wrap a page. title is escaped; body must be trusted HTML."""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body><main>{body}</main></body></html>")
