"""Stable Anki GUIDs.

The GUID is a hash of the card type + the natural key of the source content
(e.g. the Italian sentence), never of a database id. Rebuilding the database or
fixing a translation keeps the GUID, so re-importing the .apkg updates the
existing card (and its review history) instead of creating a duplicate.
"""

import genanki

NAMESPACE = "italiano-anki"


def card_guid(card_type: str, natural_key: str) -> str:
    return genanki.guid_for(NAMESPACE, card_type, natural_key)
