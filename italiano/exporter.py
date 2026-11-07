"""Read the card views and write an Anki package (.apkg) with genanki."""

from collections import Counter
from pathlib import Path

import genanki
import psycopg

from .guid import card_guid

# Fixed ids: Anki identifies decks and note types by id, so they must never change.
DECK_IDS = {
    "Italiano::Músicas": 1846203001,
    "Italiano::Frases": 1846203002,
    "Italiano::Vocabulário": 1846203003,
    "Italiano::Verbos": 1846203004,
}

CLOZE_VIEWS = ["v_card_song", "v_card_sentence", "v_card_conjugation"]

_INFO = "{{#Info}}<br><br><span class=info>{{Info}}</span>{{/Info}}"
VOCAB_MODEL = genanki.Model(
    1846203100,
    "Italiano Vocab (IT <-> PT)",
    fields=[{"name": "IT"}, {"name": "PT"}, {"name": "Info"}],
    templates=[
        {"name": "IT -> PT", "qfmt": "{{IT}}", "afmt": "{{FrontSide}}<hr id=answer>{{PT}}" + _INFO},
        {"name": "PT -> IT", "qfmt": "{{PT}}", "afmt": "{{FrontSide}}<hr id=answer>{{IT}}" + _INFO},
    ],
    css=".card { font-family: arial; font-size: 22px; text-align: center; }"
        " .info { font-size: 16px; color: #666; }",
)


def _tags(tags: list[str] | None) -> list[str]:
    """Anki tags cannot contain spaces."""
    return sorted({t.strip().replace(" ", "_") for t in tags or [] if t and t.strip()})


def build_decks(conn: psycopg.Connection) -> tuple[list[genanki.Deck], Counter]:
    decks = {name: genanki.Deck(deck_id, name) for name, deck_id in DECK_IDS.items()}
    counts: Counter = Counter()
    guids: set[str] = set()

    def add(deck: str, note: genanki.Note) -> None:
        if note.guid in guids:
            raise RuntimeError(f"duplicate GUID for note {note.fields[0]!r}")
        guids.add(note.guid)
        decks[deck].add_note(note)
        counts[deck] += 1

    for view in CLOZE_VIEWS:
        rows = conn.execute(
            f"""SELECT card_type, natural_key, deck, prefix, text_it, extra, tags
                FROM {view} ORDER BY first_seen, natural_key"""
        ).fetchall()
        for card_type, key, deck, prefix, text_it, extra, tags in rows:
            note = genanki.Note(
                model=genanki.CLOZE_MODEL,
                fields=[(prefix or "") + text_it, extra or ""],
                tags=_tags(tags),
                guid=card_guid(card_type, key),
            )
            # Gaps are added by hand in Anki. With no gap genanki would create no card at
            # all, so force card 1 (Anki shows a "no cloze found" notice until it is edited).
            note.cards = [genanki.Card(0)]
            add(deck, note)

    rows = conn.execute(
        """SELECT card_type, natural_key, deck, word_it, word_pt, info, tags
           FROM v_card_vocab ORDER BY first_seen, natural_key"""
    ).fetchall()
    for card_type, key, deck, word_it, word_pt, info, tags in rows:
        add(deck, genanki.Note(
            model=VOCAB_MODEL,
            fields=[word_it, word_pt, info or ""],
            tags=_tags(tags),
            guid=card_guid(card_type, key),
        ))

    return [d for d in decks.values() if d.notes], counts


def export_package(conn: psycopg.Connection, output: Path) -> Counter:
    decks, counts = build_decks(conn)
    if not decks:
        raise RuntimeError("no cards to export: load a lesson first")
    output.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(decks).write_to_file(str(output))
    return counts
