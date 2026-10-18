from app.routers.services_auth import _UNAVAILABLE_HTML
from app.security.nav import _NO_ACCESS_HTML
from app.security.page_style import styx_page


def test_pages_carry_the_styx_mark():
    assert 'class="mark"' in styx_page("T", "<h1>x</h1>")


def test_back_links_are_buttons():
    for page in (_UNAVAILABLE_HTML, _NO_ACCESS_HTML):
        assert '<div class="actions"><a class="btn" href="/_styx/exit" target="_top">Back to Styx</a></div>' in page
