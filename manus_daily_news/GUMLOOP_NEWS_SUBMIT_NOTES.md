# Gumloop: news_submit provenance fields (2026-09-30)

The server now checks API-key news submissions for source provenance and
compliance (see docs/content_pipeline_migration_scope.md, phase 1). While
`NEWS_SUBMIT_GATE=warn` nothing is refused; violations are stored on the item
(`compliance`) and returned in the response. When the gate is switched to
`enforce`, a submission without these is refused with a 400.

Add these arguments to the Gumloop news_submit step:

| Argument | Value |
|---|---|
| source_url | first-hand source URL (press release, company newsroom, filing) |
| source_name | e.g. "Nvidia Newsroom" |
| source_published_at | the RAW date on the source, ISO 8601 with offset |
| source_timezone | timezone that date was judged in, e.g. Asia/Tokyo |
| editorial_date | the date the run is for, YYYY-MM-DD |
| allow_stale_reason | only for background pieces on an older source; one sentence |

Run the content_lint tool on the body first and fix errors. Rules enforced:
standard disclaimer present, word band (news 1,500-1,800), no em dashes, no
bare "$" (write US$), no third-party outlet attribution, no "What is X?"
opener, no labeled ELI5/Hard Truth headings.

Switch to enforce only after a few days of runs whose `compliance.passed` is
true in the admin (News > Source provenance).
