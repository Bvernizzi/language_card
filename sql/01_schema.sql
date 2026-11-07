-- Core model. Content (sentence, vocab, conjugation) comes from a lesson,
-- from a source (song, text...), or from both: every row must have at least one.
-- Facts are stored per origin (a word seen in two lessons = two rows);
-- the card views deduplicate, so the tables keep the full history.
-- Idempotent: safe to run on every load.

CREATE TABLE IF NOT EXISTS lesson (
    lesson_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lesson_date date NOT NULL UNIQUE,
    title       text,
    notes       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Songs, texts, videos and exercises: a catalog independent of lessons.
-- Identified by a stable key from the YAML.
CREATE TABLE IF NOT EXISTS source (
    source_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_key text NOT NULL UNIQUE,
    kind       text NOT NULL CHECK (kind IN ('song', 'text', 'video', 'exercise')),
    title      text NOT NULL,
    author     text,
    url        text
);

-- Sentences from class or lines from a source. Gaps (cloze) are added by hand in Anki.
CREATE TABLE IF NOT EXISTS sentence (
    sentence_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lesson_id     integer REFERENCES lesson ON DELETE CASCADE,
    source_id     integer REFERENCES source ON DELETE CASCADE,
    text_it       text NOT NULL,
    text_pt       text,
    tags          text[] NOT NULL DEFAULT '{}',
    CONSTRAINT sentence_origin_check CHECK (lesson_id IS NOT NULL OR source_id IS NOT NULL),
    CONSTRAINT sentence_origin_key UNIQUE NULLS NOT DISTINCT (lesson_id, source_id, text_it)
);

CREATE TABLE IF NOT EXISTS vocab (
    vocab_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lesson_id      integer REFERENCES lesson ON DELETE CASCADE,
    source_id      integer REFERENCES source ON DELETE CASCADE,
    word_it        text NOT NULL,
    word_pt        text NOT NULL,
    part_of_speech text,
    gender         text CHECK (gender IN ('m', 'f', 'm/f')),
    example_it     text,
    CONSTRAINT vocab_origin_check CHECK (lesson_id IS NOT NULL OR source_id IS NOT NULL),
    CONSTRAINT vocab_origin_key UNIQUE NULLS NOT DISTINCT (lesson_id, source_id, word_it)
);

-- Dictionary of verbs (infinitive -> translation), shared by every origin.
CREATE TABLE IF NOT EXISTS verb (
    verb_id     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    infinitive  text NOT NULL UNIQUE,
    translation text
);

CREATE TABLE IF NOT EXISTS conjugation (
    conjugation_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lesson_id      integer REFERENCES lesson ON DELETE CASCADE,
    source_id      integer REFERENCES source ON DELETE CASCADE,
    verb_id        integer NOT NULL REFERENCES verb ON DELETE CASCADE,
    tense          text NOT NULL,
    person         text NOT NULL,
    form           text NOT NULL,
    CONSTRAINT conjugation_origin_check CHECK (lesson_id IS NOT NULL OR source_id IS NOT NULL),
    CONSTRAINT conjugation_origin_key
        UNIQUE NULLS NOT DISTINCT (lesson_id, source_id, verb_id, tense, person)
);
