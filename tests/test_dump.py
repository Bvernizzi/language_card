import datetime as dt
from pathlib import Path

import yaml

from italiano.dump import lesson_to_dict
from italiano.lesson_file import lesson_from_dict, parse_lesson

EXAMPLE = Path(__file__).resolve().parent.parent / "aulas" / "exemplo.yaml"


def test_yaml_round_trip_is_lossless():
    """file -> Lesson -> YAML text -> Lesson gives the same lesson."""
    original = parse_lesson(EXAMPLE)
    text = yaml.safe_dump(lesson_to_dict(original), allow_unicode=True, sort_keys=False)
    assert lesson_from_dict(yaml.safe_load(text)) == original


def test_same_verb_from_two_sources_round_trips():
    raw = {
        "date": "2026-11-07",
        "sources": [{"key": "s", "kind": "song", "title": "T"}],
        "verbs": [
            {"infinitive": "bere", "source": "s", "conjugations": {"presente": {"io": "bevo"}}},
            {"infinitive": "bere", "conjugations": {"presente": {"tu": "vieni"}}},
        ],
    }
    lesson = lesson_from_dict(raw)
    assert [c.source_key for c in lesson.conjugations] == ["s", None]
    assert lesson_from_dict(lesson_to_dict(lesson)) == lesson


def test_source_file_parses_and_round_trips():
    raw = {
        "key": "s", "kind": "song", "title": "T", "url": "https://x",
        "lines": [{"it": "Ogni mattina bevo un caffè", "pt": "Toda manhã eu bebo um café"}],
        "vocab": [{"it": "finestra", "pt": "janela"}],
        "verbs": [{"infinitive": "bere", "conjugations": {"presente": {"io": "bevo"}}}],
    }
    lesson = lesson_from_dict(raw)
    assert lesson.date is None and lesson.origin == "s"
    # every row defaults to the file's own source
    assert {lesson.sentences[0].source_key, lesson.vocab[0].source_key,
            lesson.conjugations[0].source_key} == {"s"}
    assert lesson_to_dict(lesson) == raw
    assert lesson_from_dict(lesson_to_dict(lesson)) == lesson


def test_source_without_lines_is_kept():
    raw = {"date": "2026-11-07", "sources": [{"key": "s", "kind": "song", "title": "T"}]}
    assert lesson_to_dict(lesson_from_dict(raw))["sources"] == [{"key": "s", "kind": "song", "title": "T"}]


def test_learners_round_trip():
    raw = {
        "date": dt.date(2026, 11, 7),
        "sentences": [{"it": "Ciao", "learner": "alice"}, {"it": "Buongiorno"}],
        "vocab": [{"it": "finestra", "pt": "janela", "learner": "bob"}],
        "verbs": [
            {"infinitive": "bere", "conjugations": {"presente": {"io": "bevo"}}},
            {"infinitive": "bere", "learner": "alice", "conjugations": {"presente": {"tu": "bevi"}}},
        ],
    }
    lesson = lesson_from_dict(raw)
    assert lesson_to_dict(lesson) == raw
    assert lesson_from_dict(lesson_to_dict(lesson)) == lesson


def test_source_file_of_one_learner_writes_it_once():
    raw = {"key": "s", "kind": "text", "title": "T", "learner": "alice",
           "vocab": [{"it": "finestra", "pt": "janela"}]}
    lesson = lesson_from_dict(raw)
    assert lesson.vocab[0].learner == "alice"
    lesson.learner = None  # as fetched from the DB: the file default is recomputed on dump
    from italiano.dump import _common_learner
    lesson.learner = _common_learner(lesson)
    assert lesson_to_dict(lesson) == raw
