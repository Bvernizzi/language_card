from italiano.guid import card_guid


def test_guid_is_deterministic():
    assert card_guid("sentence", "Di dove sei?") == card_guid("sentence", "Di dove sei?")


def test_guid_snapshot():
    # Guards against accidental changes to the hashing: a new GUID would make
    # Anki duplicate every card on the next import.
    assert card_guid("sentence", "Di dove sei?") == SNAPSHOT


def test_guid_depends_on_card_type_and_key():
    guids = {
        card_guid("sentence", "Di dove sei?"),
        card_guid("song", "Di dove sei?"),
        card_guid("sentence", "Di dove sei"),
    }
    assert len(guids) == 3


SNAPSHOT = "HTc0*=DtF8"
