-- One view per card type. Each view is the full rule for that card:
-- which rows become cards, the deck, the front/back composition and the tags.
-- Content may come from a lesson, a source or both (lesson is a LEFT JOIN).
-- Every view deduplicates across origins (latest lesson wins) and exposes
-- natural_key, from which Python derives a stable Anki GUID.
--
-- Cloze views share one shape:
--   card_type, natural_key, deck, prefix, text_it, extra, tags, first_seen, learners
-- learners: NULL when any occurrence is shared (learner IS NULL), else who studies it.
-- No gaps are generated: notes are exported as native Cloze notes with plain text
-- (prefix + text_it) and the gaps are added by hand in Anki.

DROP VIEW IF EXISTS v_card_song, v_card_sentence, v_card_vocab, v_card_conjugation;

-- 1. Song lines (cloze, gap added in Anki). Front: linked title + artist, line. Extra: translation.
CREATE VIEW v_card_song AS
WITH occurrences AS (
    SELECT
        so.source_key || '|' || s.text_it AS natural_key,
        s.text_it, s.text_pt, s.tags,
        so.title, so.author, so.url,
        row_number() OVER (PARTITION BY so.source_key, s.text_it
                           ORDER BY l.lesson_date DESC NULLS LAST) AS rn,
        min(l.lesson_date) OVER w AS first_seen,
        coalesce(array_agg('aula::' || l.lesson_date) FILTER (WHERE l.lesson_id IS NOT NULL) OVER w,
                 '{}') AS lesson_tags,
        CASE WHEN bool_or(s.learner IS NULL) OVER w THEN NULL
             ELSE array_agg(s.learner) OVER w END AS learners
    FROM sentence s
    JOIN source so     ON so.source_id = s.source_id
    LEFT JOIN lesson l ON l.lesson_id = s.lesson_id
    WHERE so.kind = 'song'
    WINDOW w AS (PARTITION BY so.source_key, s.text_it)
)
SELECT
    'song'::text               AS card_type,
    natural_key,
    'Italiano::Músicas'::text  AS deck,
    concat_ws(' – ',
        CASE WHEN url IS NOT NULL THEN format('<a href="%s">%s</a>', url, title) ELSE title END,
        author) || '<br><br>'  AS prefix,
    text_it,
    coalesce(text_pt, '')      AS extra,
    tags || lesson_tags        AS tags,
    first_seen,
    learners
FROM occurrences
WHERE rn = 1;

-- 2. Class sentences (cloze, gap added in Anki), including lines from non-song sources.
CREATE VIEW v_card_sentence AS
WITH occurrences AS (
    SELECT
        s.text_it AS natural_key,
        s.text_it, s.text_pt, s.tags,
        so.title, so.url,
        row_number() OVER (PARTITION BY s.text_it ORDER BY l.lesson_date DESC NULLS LAST) AS rn,
        min(l.lesson_date) OVER w AS first_seen,
        coalesce(array_agg('aula::' || l.lesson_date) FILTER (WHERE l.lesson_id IS NOT NULL) OVER w,
                 '{}') AS lesson_tags,
        CASE WHEN bool_or(s.learner IS NULL) OVER w THEN NULL
             ELSE array_agg(s.learner) OVER w END AS learners
    FROM sentence s
    LEFT JOIN source so ON so.source_id = s.source_id
    LEFT JOIN lesson l  ON l.lesson_id = s.lesson_id
    WHERE so.kind IS DISTINCT FROM 'song'
    WINDOW w AS (PARTITION BY s.text_it)
)
SELECT
    'sentence'::text          AS card_type,
    natural_key,
    'Italiano::Frases'::text  AS deck,
    CASE WHEN title IS NOT NULL THEN '<small>' || title || '</small><br><br>' END AS prefix,
    text_it,
    concat_ws('<br>', text_pt,
        CASE WHEN url IS NOT NULL THEN format('<a href="%s">%s</a>', url, title) END) AS extra,
    tags || lesson_tags       AS tags,
    first_seen,
    learners
FROM occurrences
WHERE rn = 1;

-- 3. Conjugations (cloze, gap added in Anki): "andare · passato prossimo · noi: siamo andati".
CREATE VIEW v_card_conjugation AS
WITH occurrences AS (
    SELECT
        v.infinitive || '|' || c.tense || '|' || c.person AS natural_key,
        v.infinitive, v.translation, c.tense, c.person, c.form,
        so.title AS source_title, so.author AS source_author, so.url AS source_url,
        row_number() OVER (PARTITION BY c.verb_id, c.tense, c.person
                           ORDER BY l.lesson_date DESC NULLS LAST) AS rn,
        min(l.lesson_date) OVER w AS first_seen,
        coalesce(array_agg('aula::' || l.lesson_date) FILTER (WHERE l.lesson_id IS NOT NULL) OVER w,
                 '{}') AS lesson_tags,
        CASE WHEN bool_or(c.learner IS NULL) OVER w THEN NULL
             ELSE array_agg(c.learner) OVER w END AS learners
    FROM conjugation c
    JOIN verb v         ON v.verb_id = c.verb_id
    LEFT JOIN lesson l  ON l.lesson_id = c.lesson_id
    LEFT JOIN source so ON so.source_id = c.source_id
    WINDOW w AS (PARTITION BY c.verb_id, c.tense, c.person)
)
SELECT
    'conjugation'::text       AS card_type,
    natural_key,
    'Italiano::Verbos'::text  AS deck,
    format('%s · %s · %s: ', infinitive, tense, person) AS prefix,
    form                      AS text_it,
    concat_ws('<br>',
        concat_ws(' = ', infinitive, translation),
        CASE WHEN source_title IS NOT NULL THEN
            '<small>' || concat_ws(' – ',
                CASE WHEN source_url IS NOT NULL
                     THEN format('<a href="%s">%s</a>', source_url, source_title)
                     ELSE source_title END,
                source_author) || '</small>'
        END) AS extra,
    ARRAY['verbo::' || infinitive] || lesson_tags AS tags,
    first_seen,
    learners
FROM occurrences
WHERE rn = 1;

-- 4. Vocabulary: one note, two cards (IT -> PT and PT -> IT) via a custom note type.
CREATE VIEW v_card_vocab AS
WITH occurrences AS (
    SELECT
        v.word_it, v.word_pt, v.part_of_speech, v.gender, v.example_it,
        so.title AS source_title, so.author AS source_author, so.url AS source_url,
        row_number() OVER (PARTITION BY v.word_it ORDER BY l.lesson_date DESC NULLS LAST) AS rn,
        min(l.lesson_date) OVER w AS first_seen,
        coalesce(array_agg('aula::' || l.lesson_date) FILTER (WHERE l.lesson_id IS NOT NULL) OVER w,
                 '{}') AS lesson_tags,
        CASE WHEN bool_or(v.learner IS NULL) OVER w THEN NULL
             ELSE array_agg(v.learner) OVER w END AS learners
    FROM vocab v
    LEFT JOIN lesson l  ON l.lesson_id = v.lesson_id
    LEFT JOIN source so ON so.source_id = v.source_id
    WINDOW w AS (PARTITION BY v.word_it)
)
SELECT
    'vocab'::text                  AS card_type,
    word_it                        AS natural_key,
    'Italiano::Vocabulário'::text  AS deck,
    word_it,
    word_pt,
    concat_ws('<br>',
        nullif(concat_ws(' · ', part_of_speech, gender), ''),
        '<i>' || example_it || '</i>',
        CASE WHEN source_title IS NOT NULL THEN
            concat_ws(' – ',
                CASE WHEN source_url IS NOT NULL
                     THEN format('<a href="%s">%s</a>', source_url, source_title)
                     ELSE source_title END,
                source_author)
        END) AS info,
    lesson_tags                    AS tags,
    first_seen,
    learners
FROM occurrences
WHERE rn = 1;
