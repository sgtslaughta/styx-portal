from app.services import matrix_card as mc


def test_generate_card_shape():
    card = mc.generate_card()
    assert list(card) == mc.CELLS and len(card) == 50
    for v in card.values():
        assert len(v) == 3 and set(v) <= set(mc.ALPHABET)


def test_pick_challenge_distinct():
    ch = mc.pick_challenge()
    assert len(set(ch)) == 3 and set(ch) <= set(mc.CELLS)


def test_verify_case_and_space():
    card = mc.generate_card()
    ans = [" " + card["A1"].lower() + " ", card["B2"], card["C3"]]
    assert mc.verify(card, ["A1", "B2", "C3"], ans) is True


def test_verify_one_wrong():
    card = mc.generate_card()
    assert mc.verify(card, ["A1", "B2", "C3"], [card["A1"], card["B2"], "???"]) is False


def test_verify_wrong_length():
    card = mc.generate_card()
    assert mc.verify(card, ["A1", "B2", "C3"], [card["A1"], card["B2"]]) is False


def test_seal_roundtrip():
    obj = {"A1": "ACD", "x": [1, 2]}
    assert mc.unseal(mc.seal(obj)) == obj


def test_verify_empty_challenge_fails():
    assert mc.verify(mc.generate_card(), [], []) is False


def test_verify_missing_cell_with_empty_answers_fails():
    assert mc.verify({"A1": "AAA"}, ["B2", "C3", "D4"], ["", "", ""]) is False


def test_verify_two_right_one_wrong():
    card = mc.generate_card()
    assert mc.verify(card, ["A1", "B2", "C3"], ["???", card["B2"], card["C3"]]) is False
