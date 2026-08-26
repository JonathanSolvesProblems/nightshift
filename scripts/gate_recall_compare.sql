-- Prefilter recall, old embedding against new, on the same gold set.
--
-- The question is not whether gemini-embedding-001 is a better model in the
-- abstract. It is whether swapping it in keeps more of the references a USPTO
-- examiner actually applied inside the candidate window, measured on the same
-- pairs, at the same depths.
--
-- Old: embedding_v1 from Google Patents Public Data, 64 dimensions.
-- New: gemini-embedding-001, 768 dimensions.
--
-- Produces the comparison table in ACCURACY.md.

WITH targets AS (
  SELECT DISTINCT gp.target
  FROM `prior-art-agent-2026.corpus.gold_pairs` gp
),
-- Rank of each gold reference under the ORIGINAL 64-dim embedding.
old_rank AS (
  SELECT g.target, g.ref, g.cat, COUNTIF(
    ML.DISTANCE(tv.embedding_v1, c.embedding_v1, 'COSINE') <
    ML.DISTANCE(tv.embedding_v1, rv.embedding_v1, 'COSINE')
  ) AS rank_pos
  FROM `prior-art-agent-2026.corpus.gold_pairs` g
  JOIN `prior-art-agent-2026.corpus.vectors_g06q` tv ON tv.patent_id = g.target
  JOIN `prior-art-agent-2026.corpus.vectors_g06q` rv ON rv.patent_id = g.ref
  CROSS JOIN `prior-art-agent-2026.corpus.vectors_g06q` c
  GROUP BY g.target, g.ref, g.cat
),
-- Rank of the same pairs under the 768-dim Gemini embedding.
new_rank AS (
  SELECT g.target, g.ref, g.cat, COUNTIF(
    ML.DISTANCE(tv.embedding, c.embedding, 'COSINE') <
    ML.DISTANCE(tv.embedding, rv.embedding, 'COSINE')
  ) AS rank_pos
  FROM `prior-art-agent-2026.corpus.gold_pairs` g
  JOIN `prior-art-agent-2026.corpus.vectors_gemini_g06q` tv ON tv.patent_id = g.target
  JOIN `prior-art-agent-2026.corpus.vectors_gemini_g06q` rv ON rv.patent_id = g.ref
  CROSS JOIN `prior-art-agent-2026.corpus.vectors_gemini_g06q` c
  GROUP BY g.target, g.ref, g.cat
)
SELECT
  'embedding_v1 (64d)' AS prefilter, cat, COUNT(*) AS n,
  ROUND(100 * COUNTIF(rank_pos < 1000) / COUNT(*), 1) AS recall_1k,
  ROUND(100 * COUNTIF(rank_pos < 2000) / COUNT(*), 1) AS recall_2k,
  ROUND(100 * COUNTIF(rank_pos < 5000) / COUNT(*), 1) AS recall_5k,
  ROUND(100 * COUNTIF(rank_pos < 10000) / COUNT(*), 1) AS recall_10k,
  CAST(APPROX_QUANTILES(rank_pos, 100)[OFFSET(50)] AS INT64) AS median_rank
FROM old_rank GROUP BY cat
UNION ALL
SELECT
  'gemini-embedding-001 (768d)', cat, COUNT(*),
  ROUND(100 * COUNTIF(rank_pos < 1000) / COUNT(*), 1),
  ROUND(100 * COUNTIF(rank_pos < 2000) / COUNT(*), 1),
  ROUND(100 * COUNTIF(rank_pos < 5000) / COUNT(*), 1),
  ROUND(100 * COUNTIF(rank_pos < 10000) / COUNT(*), 1),
  CAST(APPROX_QUANTILES(rank_pos, 100)[OFFSET(50)] AS INT64)
FROM new_rank GROUP BY cat
ORDER BY cat, prefilter;
