-- Effective dates for prior-art eligibility.
--
-- Section 102 turns on FILING and PRIORITY dates, not grant dates. A reference
-- granted after the target can still be valid prior art if it was filed before
-- the target's priority date, and a reference granted before the target may not
-- be prior art at all. The corpus originally carried only grant_date, which is
-- wrong in both directions.
--
-- priority_date is the earliest date the patent can claim: its own filing date,
-- any foreign priority claim, or any related US document (provisional, parent
-- continuation). MIN is the conservative choice, because an earlier priority
-- date means FEWER references qualify as prior art.
--
-- Dates are ISO strings, so lexicographic LEAST is correct.
--
-- Writes: prior-art-agent-2026.corpus.dates_g06q

WITH scope AS (
  SELECT patent_id FROM `prior-art-agent-2026.corpus.patents_g06q_clustered`
),
app AS (
  SELECT patent_id, MIN(date) AS filing_date
  FROM `patents-public-data.patentsview.application`
  WHERE patent_id IN (SELECT patent_id FROM scope)
    AND date >= '1800-01-01'
  GROUP BY patent_id
),
fp AS (
  SELECT patent_id, MIN(date) AS d
  FROM `patents-public-data.patentsview.foreign_priority`
  WHERE patent_id IN (SELECT patent_id FROM scope)
    AND date >= '1800-01-01'
  GROUP BY patent_id
),
rd AS (
  SELECT patent_id, MIN(date) AS d
  FROM `patents-public-data.patentsview.usreldoc`
  WHERE patent_id IN (SELECT patent_id FROM scope)
    AND date >= '1800-01-01'
  GROUP BY patent_id
)
SELECT
  app.patent_id,
  app.filing_date,
  LEAST(
    app.filing_date,
    IFNULL(fp.d, app.filing_date),
    IFNULL(rd.d, app.filing_date)
  ) AS priority_date
FROM app
LEFT JOIN fp USING (patent_id)
LEFT JOIN rd USING (patent_id);
