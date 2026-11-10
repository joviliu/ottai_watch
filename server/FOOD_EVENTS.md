# Lifestyle markers, concise reports and meal photos

The existing single-adult dataset and glucose/activity pipeline remain separate from annotations. New tables are additive: `lifestyle_events`, `evidence_topics`, `food_jobs`; raw glucose, revisions and older reports are preserved.

## Event API

- `GET /api/v1/events?startAt=<epoch-ms>&endAt=<epoch-ms>` accepts ingest, read or analysis capability; default is the last24h. Query window cannot exceed365days. At most1000 complete records are returned, newest first selected then chronological output; `eventsTruncated` identifies omission.
- `POST /api/v1/events` accepts ingest or analysis capability, never read-only. Body is one `{id,type,at,note,meal?,expectedUpdatedAt?}`. Types are `meal`, `sleep`, `wake`, `exercise`, `note`. IDs match `[A-Za-z0-9_-]{8,80}` (UUIDs fit). `at` is integer epoch milliseconds in the past365days through at most5minutes ahead. Note is at most1000 Unicode characters; newline/tab are permitted, other C0 controls rejected.
- Optional meal is `{foods,estimatedKcalMin,estimatedKcalMax,source}`. Foods is one editable string up to1000characters. Min/max must both be null or both finite0–20000 with min<=max. Source is `manual` or `photo_estimate`; estimate provenance is retained. A photo result only reaches glucose analysis after the user saves/updates a meal marker.
- Success is `{ok:true,event:{id,type,at,note,meal?,updatedAt}}`. Edit writes carry the prior `updatedAt` as `expectedUpdatedAt`. Exact-body retries are idempotent even if the expected revision is old; a different stale write returns409 `event_conflict`, preserving the client's draft. Writes without an expected revision cannot overwrite an existing different record.
- `POST /api/v1/events/delete` accepts `{id,expectedUpdatedAt}` and soft deletes. Already deleted/missing IDs are idempotent. A queued older create cannot silently resurrect a tombstone.

`dashboard.events` contains the most recent100 complete markers in the displayed24h plus5min tolerance; `eventsTruncated` is explicit. It does not truncate the stored note/food string. This keeps the dashboard below the Mac2,000,000-byte input bound even with long Unicode notes and dense activity. Clients needing more can use the bounded event GET.

Analysis context uses user-confirmed **approximate behavior times**, not exact physiological meal onset or measured sleep stages. It includes up to24 prioritized events per context day, with original-time local labels; long notes/food descriptions are shortened only in model input (80/120characters) with truncation flags. Raw annotation storage is unchanged. The manual snapshot hash includes all semantic events in the two-day comparison window; adding/editing/deleting an event changes the identity while exact retries do not bypass the30min attempt interval.

## Concise report v4

`methodVersion=cgm-observation-4` and `manual-v4` identities keep existing v3 ready bodies while allowing new methods to run when ordinarily eligible. New provider output uses summary<=120characters, one–three highlights `{title,text,severity,action}`, and at most one evidence item `{topic,title,text,sourceUrl}`. Severity is `info`, `watch`, or `positive`; lengths are24/120/60 for title/text/action. Legacy `sections` are constructed from highlights for old clients; new clients should not render both copies.

Generic coverage/14day/non-diagnostic paragraphs are no longer appended to the report. The prompt still uses missingness and provenance internally and only mentions a specific deficit when it changes the current conclusion. Confirmed markers distinguish actual user-entered meals from candidate excursions; unmarked excursions are not asserted as meal facts. No endocrine or medication diagnosis is inferred from a waveform.

Evidence is contextual and source URLs are restricted to the controlled source list. Introduced topic IDs are persisted separately; old ready prose explicitly mentioning Shah seeds `healthy_reference` without treating its formerly universal sources array as proof of a discussion. This records **introduced**, not that a user has necessarily understood it. Repeated foundation paragraphs are suppressed, while new relevant explanations can be shown. Sources attached to a new report only correspond to its actual evidence.

The full Responses request is bounded to256KiB for the unchanged dedicated analysis worker. Dense tests include365days of CGM, two days of1Hz HR, energy/steps/sessions and48 long Unicode event records; no oversized request is silently sent. All original event details remain in storage.

## Explicit photo recognition

`POST /api/v1/meals/recognize` accepts ingest or analysis capability only:

```json
{"requestId":"SYNTHETIC-UUID-0001","mimeType":"image/jpeg","imageBase64":"BASE64_JPEG_BYTES"}
```

The client decodes/recompresses a user-selected camera/gallery image, strips metadata, resizes to at most1024px per edge /1,048,576pixels and bounds JPEG bytes to1MiB. The server independently validates JPEG header dimensions, MIME, byte count and rejects APP1/APP13/comment metadata. JSON body is limited to1,500,000bytes. External image URLs are not accepted.

POST returns202 `{ok:true,status:"running",requestId}`. `GET /api/v1/meals/recognize?requestId=...` with the same write-capable credential returns running/ready/error. Ready includes:

```json
{"ok":true,"status":"ready","requestId":"SYNTHETIC-UUID-0001","recognition":{"isFoodImage":true,"foods":"Editable food and approximate portions","estimatedKcalMin":400,"estimatedKcalMax":650},"usage":{"usageAvailable":true,"inputTokens":1200,"outputTokens":100,"totalTokens":1300,"cachedInputTokens":200,"estimatedCostUsd":0.00151,"pricingDate":"2026-11-10","cacheHit":false}}
```

All example food and usage values are synthetic. Unknown food portions can have a null range; non-food output is normalized to empty foods and null calories. Calories are an editable rough range, not automatic precise intake. Polling does not submit another provider request; clients retain the request ID across interrupted UI sessions. Conflicting IDs return409. A completed identical-image result can be reused with zero new provider tokens/cost. An uncertain attempt is not automatically replayed. At most one unexpired food task executes at once; running tasks expire into `provider_uncertain` after150seconds if a process died. There are30 explicitly requested recognitions/day, independently of49analysis requests/day.

The JPEG travels in process memory through the dedicated Ali food relay and SG worker and is not written to the application database or logs. Only image digest, reservation/status and parsed result/usage are persisted. The broker holds an in-memory job until completion/timeout; response caches never store request images. SG sanitizes non200 provider errors so an error cannot persist echoed image/request details. Provider keys remain SG-only with systemd LoadCredential; `store:false` is not a claim about provider-side retention policy.

## Model usage and deployment

Food uses configured `gpt-6.1-terra`, Responses structured JSON, reasoning`none`, output maximum800tokens. The official[model price page](https://developers.openai.com/api/docs/models/gpt-6.1-terra) checked2026-11-10 lists Standard input$1, cached input$0.05 and output$5 per1Mtokens. Cost is an estimate from actual returned usage, not an asserted pixel-token multiplier. Missing/inconsistent usage preserves recognition with nullable counts/cost and `usageAvailable=false`; another model is not priced using Terra rates. A cached local result reports zero new tokens/cost. The app should label costs as estimates.

Daily/manual analysis retains its original Ali18779→SG18778 worker and49budget. Food uses a dedicated Ali loopback18781 relay plus SG loopback18782 tunnel/worker, its own client secrets, usage state and30budget. The provider key is loaded only by SG. Public templates are `server/deploy/ottai-food-relay.service`, `deploy/relay/ottai-food-worker.service`, and `deploy/relay/ottai-food-tunnel.service.example`; use a dedicated restricted user and SSH identity/host credential, not the education service. Node22+ is required by the reused relay modules. The SG worker accepts up to2MiB job bodies while keeping provider responses at256KiB; the original analysis worker need not be restarted for this feature.

Test locally with:

```sh
python3 -m unittest server.test_server server.test_activity server.test_lifestyle -q
python3 deploy/relay/test_worker.py
```

Tests are synthetic and do not call a provider. Back up the formal database; stop the old API before replacing its modules and prompt together, then restart. Otherwise an old process could read a new prompt while still requesting the old output schema. Actual deployment and real-device acceptance are recorded by the parent task, not inferred from these unit checks.
