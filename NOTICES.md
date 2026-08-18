# Data sources and attribution

Nightshift reads only public data. All of it is reached through the
`patents-public-data` project on Google BigQuery.

## Google Patents Public Data

`patents-public-data.patents.publications`,
`patents-public-data.google_patents_research.vector_db`

Provided by Google and IFI CLAIMS Patent Services. Licensed under
Creative Commons Attribution 4.0 International (CC BY 4.0).

## PatentsView

`patents-public-data.patentsview.*`

PatentsView is a US Patent and Trademark Office initiative. Data is in the public
domain; attribution requested.

## USPTO Office Action Citations

`patents-public-data.uspto_office_actions_citations.enriched_citations`

USPTO Office of the Chief Economist. Public domain as a work of the United States
government. This dataset is the evaluation gold standard for this project.

## USPTO PTAB trials

`patents-public-data.uspto_ptab.*`

USPTO Patent Trial and Appeal Board. Public domain.

---

## A note on what this project asserts

Nightshift reports what a prior-art reference discloses. It does not assert that
any patent is invalid, and it does not characterize any patent holder. Patent
validity is decided by a court or by the Patent Trial and Appeal Board, and
output from this tool is evidence for review by licensed patent counsel, not a
legal opinion or a substitute for one.
