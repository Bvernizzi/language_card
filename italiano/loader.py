"""Load a parsed file (lesson or source) into Postgres.

Idempotent: everything is an upsert on a natural key, and rows in the file's
scope that are no longer in the file are deleted, in one transaction.
  lesson file -> scope = rows of that lesson
  source file -> scope = rows of that source that have no lesson
"""

import datetime as dt

import psycopg

from .lesson_file import Lesson, LessonFileError


def load_lesson(conn: psycopg.Connection, lesson: Lesson) -> dict[str, int]:
    with conn.transaction():
        source_ids: dict[str, int] = {}
        for s in lesson.sources:
            source_ids[s.key] = conn.execute(
                """
                INSERT INTO source (source_key, kind, title, author, url)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source_key) DO UPDATE
                   SET kind = EXCLUDED.kind, title = EXCLUDED.title,
                       author = EXCLUDED.author, url = EXCLUDED.url
                RETURNING source_id
                """,
                (s.key, s.kind, s.title, s.author, s.url),
            ).fetchone()[0]

        if lesson.origin is None:
            lesson_id = conn.execute(
                """
                INSERT INTO lesson (lesson_date, title, notes) VALUES (%s, %s, %s)
                ON CONFLICT (lesson_date) DO UPDATE
                   SET title = EXCLUDED.title, notes = EXCLUDED.notes, updated_at = now()
                RETURNING lesson_id
                """,
                (lesson.date, lesson.title, lesson.notes),
            ).fetchone()[0]
            scope, scope_params = "t.lesson_id = %s", (lesson_id,)
        else:
            lesson_id = None
            scope = "t.lesson_id IS NULL AND t.source_id = %s"
            scope_params = (source_ids[lesson.origin],)

        def sid(key: str | None) -> int | None:
            return _source_id(conn, source_ids, key)

        def key(source_key: str | None, *parts: str) -> str:
            return "|".join([str(sid(source_key) or "")] + list(parts))

        # sentences
        for st in lesson.sentences:
            conn.execute(
                """
                INSERT INTO sentence (lesson_id, source_id, text_it, text_pt, tags, learner)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT ON CONSTRAINT sentence_origin_key DO UPDATE
                   SET text_pt = EXCLUDED.text_pt, tags = EXCLUDED.tags, learner = EXCLUDED.learner
                """,
                (lesson_id, sid(st.source_key), st.text_it, st.text_pt, st.tags, st.learner),
            )
        conn.execute(
            f"""DELETE FROM sentence t WHERE {scope}
                  AND NOT (coalesce(t.source_id::text, '') || '|' || t.text_it = ANY(%s::text[]))""",
            (*scope_params, [key(s.source_key, s.text_it) for s in lesson.sentences]),
        )

        # vocab
        for v in lesson.vocab:
            conn.execute(
                """
                INSERT INTO vocab (lesson_id, source_id, word_it, word_pt, part_of_speech, gender,
                                   example_it, learner)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ON CONSTRAINT vocab_origin_key DO UPDATE
                   SET word_pt = EXCLUDED.word_pt, part_of_speech = EXCLUDED.part_of_speech,
                       gender = EXCLUDED.gender, example_it = EXCLUDED.example_it,
                       learner = EXCLUDED.learner
                """,
                (lesson_id, sid(v.source_key), v.word_it, v.word_pt, v.part_of_speech, v.gender,
                 v.example_it, v.learner),
            )
        conn.execute(
            f"""DELETE FROM vocab t WHERE {scope}
                  AND NOT (coalesce(t.source_id::text, '') || '|' || t.word_it = ANY(%s::text[]))""",
            (*scope_params, [key(v.source_key, v.word_it) for v in lesson.vocab]),
        )

        # verbs (dictionary) and conjugations
        verb_ids = {}
        for v in lesson.verbs:
            verb_ids[v.infinitive] = conn.execute(
                """
                INSERT INTO verb (infinitive, translation) VALUES (%s, %s)
                ON CONFLICT (infinitive) DO UPDATE
                   SET translation = coalesce(EXCLUDED.translation, verb.translation)
                RETURNING verb_id
                """,
                (v.infinitive, v.translation),
            ).fetchone()[0]
        for c in lesson.conjugations:
            conn.execute(
                """
                INSERT INTO conjugation (lesson_id, source_id, verb_id, tense, person, form, learner)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ON CONSTRAINT conjugation_origin_key DO UPDATE
                   SET form = EXCLUDED.form, learner = EXCLUDED.learner
                """,
                (lesson_id, sid(c.source_key), verb_ids[c.infinitive], c.tense, c.person, c.form,
                 c.learner),
            )
        conn.execute(
            f"""DELETE FROM conjugation t USING verb v
                 WHERE t.verb_id = v.verb_id AND {scope}
                   AND NOT (coalesce(t.source_id::text, '') || '|' || v.infinitive || '|'
                            || t.tense || '|' || t.person = ANY(%s::text[]))""",
            (*scope_params,
             [key(c.source_key, c.infinitive, c.tense, c.person) for c in lesson.conjugations]),
        )

        _delete_orphan_verbs(conn)

    return {
        "sentences": len(lesson.sentences),
        "vocab": len(lesson.vocab),
        "conjugations": len(lesson.conjugations),
    }


def _source_id(conn: psycopg.Connection, source_ids: dict, key: str | None) -> int | None:
    """Resolve a source key from this file, or from a source already in the database."""
    if key is None:
        return None
    if key not in source_ids:
        row = conn.execute("SELECT source_id FROM source WHERE source_key = %s", (key,)).fetchone()
        if row is None:
            raise LessonFileError(f"unknown source {key!r}: define it under 'sources' or load its file")
        source_ids[key] = row[0]
    return source_ids[key]


def remove_lesson(conn: psycopg.Connection, date: dt.date) -> bool:
    """Delete a lesson and its rows (cascade).

    Sources used by this lesson are deleted too if nothing else references them.
    """
    with conn.transaction():
        used = [r[0] for r in conn.execute(
            """SELECT t.source_id FROM (
                   SELECT lesson_id, source_id FROM sentence
                   UNION ALL SELECT lesson_id, source_id FROM vocab
                   UNION ALL SELECT lesson_id, source_id FROM conjugation) t
                JOIN lesson l USING (lesson_id)
               WHERE l.lesson_date = %s AND t.source_id IS NOT NULL""",
            (date,),
        )]
        deleted = conn.execute("DELETE FROM lesson WHERE lesson_date = %s", (date,)).rowcount
        conn.execute(
            """DELETE FROM source so WHERE so.source_id = ANY(%s::int[])
                 AND NOT EXISTS (SELECT 1 FROM sentence t WHERE t.source_id = so.source_id)
                 AND NOT EXISTS (SELECT 1 FROM vocab t WHERE t.source_id = so.source_id)
                 AND NOT EXISTS (SELECT 1 FROM conjugation t WHERE t.source_id = so.source_id)""",
            (used,),
        )
        _delete_orphan_verbs(conn)
    return deleted > 0


def _delete_orphan_verbs(conn: psycopg.Connection) -> None:
    conn.execute(
        "DELETE FROM verb v WHERE NOT EXISTS (SELECT 1 FROM conjugation c WHERE c.verb_id = v.verb_id)"
    )
