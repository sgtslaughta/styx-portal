from app.security.page_style import styx_page


def test_page_has_tokens_and_both_schemes():
    html = styx_page("No access", "<p>x</p>")
    assert "#0F1C22" in html and "#EDF1EF" in html and "prefers-color-scheme" in html
    assert "<title>No access</title>" in html


def test_title_is_escaped():
    assert "<title>&lt;script&gt;</title>" in styx_page("<script>", "")
