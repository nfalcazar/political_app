# Evidence policy

## Evidence is attributed, not universal

An evidence unit records what a particular primary source reports within a specific population, geography, timeframe, method, and locator. It is not stored as an unqualified fact.

## Discovery versus evidence

News, commentary, think-tank summaries, and advocacy pages can reveal arguments or citations. They remain discovery sources. Their claims cannot appear as dossier evidence unless the referenced primary source is retrieved and checked.

Primary sources include original research, official datasets and reports, legislation, statutes, court records, and official releases or testimony. A domain heuristic only creates a candidate classification; it does not itself validate authority or quality.

## Rights-aware retention

Retrieval permission and copyright status are separate from evidentiary quality. Unknown rights are treated conservatively. Full text from copyrighted or unknown-rights sources is a private processing cache that expires within 24 hours and is deleted after successful extraction. Durable full-text archives require a recorded public-domain, open-license, or permission basis.

The durable research record contains an original factual summary, a necessary short quotation, a stable locator, source provenance, access date, rights status, and the canonical source link. There is no purported universally safe quotation length. Authentication, paywalls, DRM, blocklists, and disallowing robots policies are not bypassed.

## Conflicts and uncertainty

Supporting, challenging, and mixed results remain separate. The application does not resolve disagreement by majority count. Confidence describes extraction and source match quality, not ideological usefulness.

## Model constraints

- Terminal plans require human approval. In the local citizen-facing prototype,
  submitting a claim authorizes one bounded automatically generated plan; its scope
  and limits remain inspectable and the authorization is recorded with the project.
- Extracted quotations must occur verbatim in the stored source chunk.
- Findings that substantially reproduce the selected quotation are rejected as overly close summaries.
- Lexical matching and optional embeddings only produce review candidates.
- The system never automatically revises or narrows a thesis.
- A user explicitly pauses, revises, or continues after the evidence checkpoint.
