from app.security.csrf import new_csrf_token, csrf_valid


def test_matching_tokens_valid():
    t = new_csrf_token()
    assert csrf_valid(cookie=t, header=t) is True


def test_mismatch_invalid():
    assert csrf_valid(cookie=new_csrf_token(), header=new_csrf_token()) is False


def test_missing_invalid():
    assert csrf_valid(cookie=None, header="x") is False
    assert csrf_valid(cookie="x", header=None) is False
