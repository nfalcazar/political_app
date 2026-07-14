# Deprecated RSS pipeline

Everything in this `app` directory belongs to the previous RSS-driven claim stream. It is retained only as a behavioral reference while the new thesis-driven workflow receives live validation.

The active `research_app` package must never import this directory. Running `app/pol_app.py` emits a deprecation warning.

## Retained components and replacements

| Legacy component | Temporary reason | Replacement |
| --- | --- | --- |
| `pol_app.py`, `text_processor.py`, `data_processor.py` | Last integrated RSS flow | `research_app.researcher` and CLI |
| `database/` | Reference for the prototype database | `research_app.models` and `repository` |
| `routines/grab_rss_feeds.py` | Possible future refresh input | Targeted search and source retrieval |
| `routines/resolve_sources.py` | Search-query and source-resolution reference | Search provider and discovery links |
| `db_graph_visual.py` and `lib/` | Prototype relationship viewer | Markdown dossier; future UI is out of MVP scope |
| `prompts/` | Historical extraction prompts | Structured planner/extractor prompts in active services |

Superseded collectors, crawler prototypes, scratch tests, old notes, and all of `feature_dev` were deleted. They remain recoverable from Git commit `9ecd3e1`.

## Deletion criterion

Delete this entire directory after a credentialed labor-union research run demonstrates:

1. approved-plan search and resume;
2. primary-source HTML and PDF retrieval;
3. supporting and challenging evidence extraction;
4. no duplicate work on rerun;
5. a dossier regenerated with network and model access disabled; and
6. the automated suite still passing.

No active code changes should be made here. Fixes belong in `research_app`.

