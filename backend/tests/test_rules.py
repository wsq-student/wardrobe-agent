from app.agent import validate_outfit, edit_constraints

ITEMS = [dict(id=1, category='tops', status='available'), dict(id=2, category='bottoms', status='available'),
         dict(id=3, category='outerwear', status='washing'), dict(id=4, category='one-pieces', status='available')]


def test_valid_outfit():
    assert validate_outfit({'item_ids': [1, 2]}, ITEMS) == []
    assert validate_outfit({'item_ids': [4]}, ITEMS) == []


def test_hallucinated_and_unavailable_items():
    assert validate_outfit({'item_ids': [1, 2, 999]}, ITEMS)
    assert validate_outfit({'item_ids': [1, 2, 3]}, ITEMS)


def test_duplicate_and_incompatible_items():
    assert validate_outfit({'item_ids': [1, 1, 2]}, ITEMS)
    assert validate_outfit({'item_ids': [1, 2, 4]}, ITEMS)
    assert validate_outfit({'item_ids': [1]}, ITEMS)


def test_empty_closet_can_clarify():
    assert validate_outfit({'item_ids': []}, []) == []


def test_only_replace_shoes_keeps_other_slots():
    import json
    items = ITEMS + [dict(id=5,category='shoes',status='available'), dict(id=6,category='shoes',status='available')]
    locked, replaced = edit_constraints('只换一双鞋', [{'role':'assistant','content':json.dumps({'item_ids':[1,2,5]})}], items)
    assert locked == [1,2]
    assert replaced == [5]
    assert not validate_outfit({'item_ids':[1,2,6]}, items, locked, replaced)
    assert validate_outfit({'item_ids':[4,6]}, items, locked, replaced)
    assert validate_outfit({'item_ids':[1,2,5]}, items, locked, replaced)
