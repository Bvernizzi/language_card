"""Parse and validate a lesson YAML file into plain dataclasses (no database)."""

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml


SOURCE_KINDS = {"song", "text", "video", "exercise"}
GENDERS = {"m", "f", "m/f"}


class LessonFileError(ValueError):
    pass


@dataclass
class Source:
    key: str
    kind: str
    title: str
    author: str | None = None
    url: str | None = None


@dataclass
class Sentence:
    text_it: str
    text_pt: str | None
    tags: list[str]
    source_key: str | None = None
    learner: str | None = None


@dataclass
class Vocab:
    word_it: str
    word_pt: str
    part_of_speech: str | None = None
    gender: str | None = None
    example_it: str | None = None
    source_key: str | None = None
    learner: str | None = None


@dataclass
class Conjugation:
    infinitive: str
    tense: str
    person: str
    form: str
    source_key: str | None = None
    learner: str | None = None


@dataclass
class Verb:
    infinitive: str
    translation: str | None
    source_key: str | None = None
    learner: str | None = None


@dataclass
class Lesson:
    """Content of one YAML file.

    Lesson file (has `date`): content seen in a class.
    Source file (has `key`, date is None): content taken only from a source;
    `origin` is that source's key and every row defaults to it.
    """
    date: dt.date | None
    title: str | None = None
    notes: str | None = None
    sources: list[Source] = field(default_factory=list)
    sentences: list[Sentence] = field(default_factory=list)
    vocab: list[Vocab] = field(default_factory=list)
    verbs: list[Verb] = field(default_factory=list)
    conjugations: list[Conjugation] = field(default_factory=list)
    origin: str | None = None
    learner: str | None = None  # file default; each row keeps its own value

    @property
    def label(self) -> str:
        return self.date.isoformat() if self.date else f"source {self.origin}"


def parse_lesson(path: str | Path) -> Lesson:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        return lesson_from_dict(raw)
    except LessonFileError as exc:
        raise LessonFileError(f"{path.name}: {exc}") from None


def _str(value) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _require(item: dict, key: str, where: str) -> str:
    value = _str(item.get(key)) if isinstance(item, dict) else None
    if value is None:
        raise LessonFileError(f"{where}: missing '{key}'")
    return value


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _learner(item, default: str | None) -> str | None:
    """Row value if the key is present (an explicit empty value = shared), else the file default."""
    if isinstance(item, dict) and "learner" in item:
        return _str(item["learner"])
    return default


def _sentence(item: dict, where: str, source_key: str | None, learner: str | None) -> Sentence:
    if isinstance(item, dict) and "cloze" in item:
        raise LessonFileError(f"{where}: 'cloze' is no longer stored; add gaps by hand in Anki")
    return Sentence(
        text_it=_require(item, "it", where),
        text_pt=_str(item.get("pt")),
        tags=[str(t) for t in _as_list(item.get("tags"))],
        source_key=source_key,
        learner=_learner(item, learner),
    )


def _source(item: dict, where: str) -> Source:
    kind = _require(item, "kind", where)
    if kind not in SOURCE_KINDS:
        raise LessonFileError(f"{where}: kind must be one of {sorted(SOURCE_KINDS)}")
    return Source(
        key=_require(item, "key", where),
        kind=kind,
        title=_require(item, "title", where),
        author=_str(item.get("author")),
        url=_str(item.get("url")),
    )


def _date(value) -> dt.date:
    if isinstance(value, str):
        try:
            value = dt.date.fromisoformat(value)
        except ValueError:
            raise LessonFileError(f"invalid date {value!r}, use YYYY-MM-DD") from None
    if not isinstance(value, dt.date):
        raise LessonFileError("missing 'date' (YYYY-MM-DD)")
    return value


def lesson_from_dict(raw) -> Lesson:
    if not isinstance(raw, dict):
        raise LessonFileError("the file must be a YAML mapping")

    if "date" in raw or "key" not in raw:  # lesson file
        lesson = Lesson(date=_date(raw.get("date")), title=_str(raw.get("title")),
                        notes=_str(raw.get("notes")), learner=_str(raw.get("learner")))
        for i, item in enumerate(_as_list(raw.get("sources")), start=1):
            source = _source(item, f"sources[{i}]")
            lesson.sources.append(source)
            for j, line in enumerate(_as_list(item.get("lines")), start=1):
                lesson.sentences.append(_sentence(line, f"sources[{i}].lines[{j}]", source.key,
                                                   lesson.learner))
        for i, item in enumerate(_as_list(raw.get("sentences")), start=1):
            lesson.sentences.append(_sentence(item, f"sentences[{i}]", None, lesson.learner))
    else:  # source file
        source = _source(raw, "source")
        lesson = Lesson(date=None, sources=[source], origin=source.key,
                        learner=_str(raw.get("learner")))
        for j, line in enumerate(_as_list(raw.get("lines")), start=1):
            lesson.sentences.append(_sentence(line, f"lines[{j}]", source.key, lesson.learner))

    for i, item in enumerate(_as_list(raw.get("vocab")), start=1):
        where = f"vocab[{i}]"
        gender = _str(item.get("gender"))
        if gender is not None and gender not in GENDERS:
            raise LessonFileError(f"{where}: gender must be one of {sorted(GENDERS)}")
        lesson.vocab.append(Vocab(
            word_it=_require(item, "it", where),
            word_pt=_require(item, "pt", where),
            part_of_speech=_str(item.get("pos")),
            gender=gender,
            example_it=_str(item.get("example")),
            source_key=_str(item.get("source")) or lesson.origin,
            learner=_learner(item, lesson.learner),
        ))

    for i, item in enumerate(_as_list(raw.get("verbs")), start=1):
        where = f"verbs[{i}]"
        infinitive = _require(item, "infinitive", where)
        source_key = _str(item.get("source")) or lesson.origin  # optional source key
        learner = _learner(item, lesson.learner)
        lesson.verbs.append(Verb(infinitive, _str(item.get("pt")), source_key, learner))
        conjugations = item.get("conjugations") or {}
        if not isinstance(conjugations, dict):
            raise LessonFileError(f"{where}: conjugations must map tense -> person -> form")
        for tense, persons in conjugations.items():
            if not isinstance(persons, dict):
                raise LessonFileError(f"{where}.{tense}: must map person -> form")
            for person, form in persons.items():
                if _str(form) is None:
                    raise LessonFileError(f"{where}.{tense}.{person}: empty form")
                lesson.conjugations.append(
                    Conjugation(infinitive, str(tense).strip(), str(person).strip(), _str(form),
                                source_key, learner)
                )

    _check_unique([s.key for s in lesson.sources], "source key")
    _check_unique([s.text_it for s in lesson.sentences], "sentence")
    _check_unique([v.word_it for v in lesson.vocab], "vocab word")
    # a verb may appear twice only with different sources or learners
    _check_unique([f"{v.infinitive} (source: {v.source_key}, learner: {v.learner})"
                   for v in lesson.verbs], "verb")
    _check_unique([f"{c.infinitive} · {c.tense} · {c.person}" for c in lesson.conjugations],
                  "conjugation")
    return lesson


def _check_unique(values: list[str], what: str) -> None:
    seen = set()
    for value in values:
        if value in seen:
            raise LessonFileError(f"duplicate {what}: {value!r}")
        seen.add(value)
