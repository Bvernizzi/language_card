import datetime as dt
from pathlib import Path

import pytest

from italiano.lesson_file import LessonFileError, lesson_from_dict, parse_lesson

EXAMPLE = Path(__file__).resolve().parent.parent / "aulas" / "exemplo.yaml"


def test_example_file_parses():
    lesson = parse_lesson(EXAMPLE)
    assert lesson.date == dt.date(2000, 1, 1)
    assert {s.key for s in lesson.sources} == {"canzone-del-caffe", "dialogo-al-bar"}
    song_lines = [s for s in lesson.sentences if s.source_key == "canzone-del-caffe"]
    assert len(song_lines) == 2
    assert song_lines[1].text_pt == "E o sol entra pela janela"
    assert len(lesson.vocab) == 3
    assert ("andare", "passato prossimo", "noi", "siamo andati") in {
        (c.infinitive, c.tense, c.person, c.form) for c in lesson.conjugations
    }


def test_date_is_required():
    with pytest.raises(LessonFileError, match="date"):
        lesson_from_dict({"title": "x"})


def test_cloze_is_rejected_gaps_are_made_in_anki():
    with pytest.raises(LessonFileError, match="Anki"):
        lesson_from_dict({"date": "2026-11-06", "sentences": [{"it": "Ciao a tutti", "cloze": "Ciao"}]})


def test_duplicate_sentence_is_rejected():
    s = {"it": "Ciao"}
    with pytest.raises(LessonFileError, match="duplicate"):
        lesson_from_dict({"date": "2026-11-06", "sentences": [s, s]})


def test_invalid_source_kind():
    with pytest.raises(LessonFileError, match="kind"):
        lesson_from_dict({"date": "2026-11-06", "sources": [{"key": "a", "kind": "podcast", "title": "x"}]})


def test_learner_file_default_and_row_override():
    lesson = lesson_from_dict({
        "date": "2026-11-06",
        "learner": "alice",
        "sentences": [{"it": "Ciao"}, {"it": "Buongiorno", "learner": None}],  # null = shared
        "vocab": [{"it": "finestra", "pt": "janela", "learner": "bob"}],
        "verbs": [{"infinitive": "bere", "conjugations": {"presente": {"io": "bevo"}}}],
    })
    assert [s.learner for s in lesson.sentences] == ["alice", None]
    assert lesson.vocab[0].learner == "bob"
    assert lesson.conjugations[0].learner == "alice"


def test_payment_is_validated():
    assert lesson_from_dict({"date": "2026-11-13", "payment": "paid"}).payment == "paid"
    with pytest.raises(LessonFileError, match="payment"):
        lesson_from_dict({"date": "2026-11-13", "payment": "maybe"})
