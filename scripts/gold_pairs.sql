-- Build the evaluation gold set.
--
-- A gold pair is (target patent, prior-art reference) where a USPTO examiner
-- APPLIED that reference in a rejection of the target's own application.
--
-- The filter is citationCategoryCode, not examinerCitedReferenceIndicator.
-- That flag means "listed on the USPTO 892 form", not "used in a rejection":
-- 67.4% of its rows are category A ("not prejudicial to novelty"), and it omits
-- 1,216,172 category-X rows whose indicator is NULL, 44% of all anticipation
-- citations in the dataset.
--
--   X = claimed invention cannot be considered novel        (§102)
--   Y = not inventive when combined with another reference  (§103)
--   A = background only, excluded
--
-- A pair qualifies only if both sides are in the corpus, both have issued claim
-- text, and both have an embedding, so the agent could in principle find it.
--
-- Writes: prior-art-agent-2026.corpus.gold_pairs

WITH ev AS (
  SELECT c.patent_id AS target, SAFE_CAST(a.number AS INT64) AS app
  FROM `prior-art-agent-2026.corpus.patents_g06q_clustered` c
  JOIN `patents-public-data.patentsview.application` a
    ON a.patent_id = c.patent_id
  WHERE ARRAY_LENGTH(c.claims) > 0
),
gold AS (
  SELECT
    ev.target,
    REGEXP_EXTRACT(e.citedDocumentIdentifier, r'^US ([0-9]{7,8}) ') AS ref,
    e.citationCategoryCode AS cat
  FROM ev
  JOIN `patents-public-data.uspto_office_actions_citations.enriched_citations` e
    ON e.patentApplicationNumber = ev.app
  WHERE e.citationCategoryCode IN ('X', 'Y')
    AND REGEXP_CONTAINS(e.citedDocumentIdentifier, r'^US [0-9]{7,8} ')
)
SELECT DISTINCT g.target, g.ref, g.cat
FROM gold g
JOIN `prior-art-agent-2026.corpus.patents_g06q_clustered` r ON r.patent_id = g.ref
JOIN `prior-art-agent-2026.corpus.vectors_g06q` vt ON vt.patent_id = g.target
JOIN `prior-art-agent-2026.corpus.vectors_g06q` vr ON vr.patent_id = g.ref
WHERE ARRAY_LENGTH(r.claims) > 0
  AND g.ref != g.target;
