-- Prefilter recall gate.
--
-- Question: does the coarse vector stage keep the reference a USPTO examiner
-- actually applied in a rejection, out of 171,695 corpus patents?
--
-- The judgment stage can only find what this stage keeps, so this is a ceiling
-- on the whole pipeline and the justification for judging thousands of
-- candidates rather than tens.
--
-- Produces the table in ACCURACY.md, Result 1.
-- Run: bq query --use_legacy_sql=false < scripts/gate_recall.sql

WITH targets AS (
  SELECT DISTINCT gp.target, v.embedding_v1 AS tvec
  FROM `prior-art-agent-2026.corpus.gold_pairs` gp
  JOIN `prior-art-agent-2026.corpus.vectors_g06q` v
    ON v.patent_id = gp.target
),
gold AS (
  SELECT
    gp.target,
    gp.ref,
    gp.cat,
    ML.DISTANCE(t.tvec, vr.embedding_v1, 'COSINE') AS gold_dist
  FROM `prior-art-agent-2026.corpus.gold_pairs` gp
  JOIN targets t ON t.target = gp.target
  JOIN `prior-art-agent-2026.corpus.vectors_g06q` vr ON vr.patent_id = gp.ref
),
-- Rank of the gold reference = how many corpus patents sit closer to the target.
ranked AS (
  SELECT
    g.target,
    g.ref,
    g.cat,
    COUNTIF(ML.DISTANCE(t.tvec, c.embedding_v1, 'COSINE') < g.gold_dist) AS rank_pos
  FROM gold g
  JOIN targets t ON t.target = g.target
  CROSS JOIN `prior-art-agent-2026.corpus.vectors_g06q` c
  GROUP BY g.target, g.ref, g.cat
)
SELECT
  cat,
  COUNT(*) AS n,
  ROUND(100 * COUNTIF(rank_pos < 1000) / COUNT(*), 1) AS recall_at_1k,
  ROUND(100 * COUNTIF(rank_pos < 5000) / COUNT(*), 1) AS recall_at_5k,
  ROUND(100 * COUNTIF(rank_pos < 10000) / COUNT(*), 1) AS recall_at_10k,
  ROUND(100 * COUNTIF(rank_pos < 25000) / COUNT(*), 1) AS recall_at_25k,
  CAST(APPROX_QUANTILES(rank_pos, 100)[OFFSET(50)] AS INT64) AS median_rank
FROM ranked
GROUP BY cat
ORDER BY cat;
