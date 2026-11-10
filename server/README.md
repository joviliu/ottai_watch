# Private Ottai collection service

Python 3.6+ standard library only. One intended adult's readings are stored in a dedicated SQLite database, independent of other applications. The API binds loopback and is exposed by the existing validated HTTPS reverse proxy; clients must verify TLS normally. Credentials remain in a root-owned EnvironmentFile and each client's private configuration.

## API

Use `Authorization: Bearer <token>`. `INGEST_TOKEN` may upload and read; the separate `READ_TOKEN` may only read. Both must be at least 32 characters and different. No account identifier is necessary for this explicitly single-user deployment; do not reuse the service for multiple users without adding account isolation.

- `POST /api/v1/readings`: JSON `{"readings":[{"sourceAt":1794200000000,"value":6.2,"trend":"→"}]}`. The timestamp/example value is synthetic. Maximum 1,000 points and 256 KiB. Values follow the existing Android validator: finite, greater than zero and at most 60 mmol/L; timestamp is an integer greater than zero and at most 90 seconds into the future. Trend accepts `?` or up to 32 glyphs from the phone parser's arrow set, preserving repeated arrows without inventing a different trend; other strings are rejected. Whole batches are validated before one atomic SQLite transaction.
- Success returns `{"ok":true,"serverAt":...,"accepted":N,"inserted":... ,"corrected":...,"unchanged":...}`. `accepted` includes all valid rows, including duplicate/resend rows; the uploader may acknowledge the exact batch. `sourceAt` is the idempotency key. Later value/trend corrections update the current row and append an audit revision. An optional boolean `historical:true` inserts missing history but never overwrites an existing row with unknown trend.
- `GET /api/v1/dashboard`: `{schemaVersion,serverAt,latest,readings,metrics,comparison,analysis}`. `latest` is null before the first reading. `readings` contains the latest 24-hour raw curve. Missing numeric statistics are null, not zero. `metrics` is the latest rolling 24 hours; `comparison.points` is historical same-time-of-day median/p25/p75, using earlier 28 days and excluding the latest 24 hours. `analysis` is waiting/ready/error with summary, sections, limitations and fixed scientific sources. An old ready report remains visible if a later daily attempt fails, with its original report date.
- `GET /health`: unauthenticated non-sensitive liveness only. It does not call a model.

For the public reverse-proxy mount `/ottai/`, clients append `/api/v1/...` to their base URL; the proxy strips the mount prefix before reaching this service.

## Observation methods

Every raw value receives at most the following nominal five minutes of time weight; the next observation can shorten that interval. Long gaps remain missing, never interpolated. Means, population SD, CV and range percentages use observed time only, with coverage separately stated. Min/max refer to observed values. The user range 3.9–7.8 is explicitly observational, not an individualized medical target; the separate 3.9–10.0 statistic is labeled as a diabetes-population reference. No GMI/estimated HbA1c or CGM diagnosis is produced.

Historical display buckets are 30 minutes: calculate each day's within-bucket median, then the across-day median and quartiles. This avoids a day with more packets overwhelming the reference. They are descriptive references, not interpolated missing values. The report reads up to 365 days and receives raw recent 24-hour pairs, window metrics, compact daily summaries up to 56 days and non-overlapping 28-day block summaries for older data (at most 12, with the final partial block's actual duration labeled). Missingness and coverage remain explicit; raw data is not deleted or smoothed to calculate the metrics. Program-supplied comparison availability and 72-hour coverage distinguish a long timestamp span from genuinely collected hours.

## Daily analysis

`python3 -m server.app run-daily` is a separate bounded oneshot, invoked by a systemd timer at 08:15 Asia/Shanghai, covering the previous local calendar day 00:00–24:00. There is no weekly model job. Every report considers 24-hour, 7-day, 14-day and older comparisons where available; insufficient or incomparable windows must be called out.

`ANALYSIS_ENABLED` defaults false. The adult's data span must exceed 72 hours before a scheduled request is made; three days is a provisional reporting threshold, not evidence that the dataset represents a stable longer-term pattern. If no source point falls within the latest 24 hours, the job returns `no_recent_data` without a model request or claiming the day; cached values/reports remain explicitly historical. A unique SQLite report-date claim is committed before network I/O. At most one scheduled model attempt per calendar report-date is automatically made, even after timeout/restart; unknown results are not retried. Failed reports do not interrupt ingestion or reading. No synthetic history is mixed into the live database to satisfy the threshold.

The model call uses `/v1/responses`, `store:false`, structured JSON and the generic relay's HMAC-SHA256 contract. `OPENAI_RELAY_URL` must be loopback HTTP; proxy environment settings and redirects are disabled. Service identity, exact path/body, content type, timestamp, nonce and stable daily request ID are signed. The service never holds or chooses an OpenAI provider key. `OPENAI_MODEL` is an environment setting, not user-supplied API input. Scientific source links are program-controlled rather than model-generated. Review [daily_prompt.md](daily_prompt.md) with the root scientific-method documentation before enabling.

The database, WAL, audit rows, reports and upstream replies are private health data. No request paths, bearer tokens, readings or model bodies are emitted in normal logs. `run-daily` prints only status/date/error code. Back up SQLite using a consistent database backup procedure, including its WAL if copying an active database; never copy just the active main file. Deployment and actual-device validation are performed by the parent task.

## Run and test

```sh
python3 -m unittest server.test_server -v
# With private environment loaded and database directory owned by the service user:
python3 -m server.app serve
```

Systemd service/timer and reverse-proxy examples are in [deploy](deploy). They use `/srv/ottai-cloud/app`, `/etc/ottai-cloud/service.env` and `/var/lib/ottai-cloud`. Adapt these explicit paths when installing; no real credentials or health database belongs in Git. No test in this directory contacts a model or live account.

## Rolling manual analysis (0.3.0)

`POST /api/v1/analysis` has an empty body and accepts the separate `ANALYZE_TOKEN` capability (or device ingest token); `READ_TOKEN` is rejected. The capability cannot read the dashboard or upload readings. The Mac host holds both read and analysis capabilities; the sandboxed Widget only receives the read token. Do not reuse token values.

Eligibility requires 24h of source span, >=95% observed coverage, no unobserved gap >15min and a source reading in the last 10min. These are explicit product completeness rules, not a validated clinical threshold. The rolling report ends at the latest source measurement, not an invented current value. It has its own `manual_reports` table and snapshot hash, separate from fixed calendar-day reports. A correction to the recent data changes its snapshot identity. A persistent SQLite transaction enforces at least 30min between attempts across clients/restarts; the same snapshot is not sent twice, including an uncertain/error result. There is no additional small daily manual limit; the rate implies at most 48 manual attempts/day. Relay/client/SG daily safety caps are 49 for these plus one scheduled report, with original counters preserved.

The endpoint claims before spawning bounded work and immediately returns 202. Clients poll dashboard status; a failed POST must be followed by a status read rather than an automatic paid retry. Dashboard adds `manualAnalysis` (eligibility/state), `rollingAnalysis`, `dailyAnalysis`; the legacy `analysis` field contains the most recently generated result for older clients. The two report bodies retain their own period/trigger and never overwrite one another.

`excursions.py` computes descriptive candidate rises/recoveries without bridging >10min source gaps. A 3-point median locates sustained peaks; whole-window statistics retain original samples. Thresholds are documented heuristics, not validated meal detection or endocrine diagnostics. Censored recovery remains null. The prompt distinguishes observed shapes, approximate meal-review anchors, alternatives and verification; no hormone amount/function or unhealthy diet is inferred as fact. Healthy research descriptors and personal complete-day baselines are explicitly labeled and coverage qualified. See the scientific-method document for primary sources.
