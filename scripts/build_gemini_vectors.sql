-- Re-embed the corpus with gemini-embedding-001.
--
-- Why this exists. The measured loss in the pipeline is almost entirely in
-- retrieval, not in judgment: the prefilter drops 21.8% of anticipation
-- references before the model ever reads them, while the model misses only 2.5%
-- of what reaches it (ACCURACY.md).
--
-- The original prefilter used `embedding_v1` from Google Patents Public Data:
-- 64 dimensions, produced by an unpublished model with no callable endpoint, so
-- nothing new can ever be projected into that space. This replaces it with 768
-- dimensions from a model that is callable, which also means a query no longer
-- has to be an existing corpus patent.
--
-- Text is title plus the first 2,000 characters of the disclosure, which is the
-- abstract followed by the claims. Claims are what prior art is matched against,
-- so they belong in the embedded text rather than the abstract alone.
--
-- Writes: prior-art-agent-2026.corpus.vectors_gemini_g06q

CREATE OR REPLACE TABLE `prior-art-agent-2026.corpus.vectors_gemini_g06q`
CLUSTER BY patent_id AS
SELECT
  patent_id,
  ml_generate_embedding_result AS embedding
FROM ML.GENERATE_EMBEDDING(
  MODEL `prior-art-agent-2026.corpus.embedder`,
  (
    SELECT
      patent_id,
      CONCAT(IFNULL(title, ''), '. ', SUBSTR(IFNULL(disclosure, ''), 1, 2000)) AS content
    FROM `prior-art-agent-2026.corpus.patents_g06q_clustered`
  ),
  STRUCT(
    TRUE AS flatten_json_output,
    'RETRIEVAL_DOCUMENT' AS task_type,
    768 AS output_dimensionality
  )
)
WHERE ARRAY_LENGTH(ml_generate_embedding_result) = 768;
