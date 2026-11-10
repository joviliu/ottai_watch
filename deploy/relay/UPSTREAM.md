# Relay reuse

The four unmodified JavaScript modules in `vendor/` are from the user's
[cloud_level_up](https://github.com/joviliu/cloud_level_up) project at commit
`2695ff3f57be7c9dbad55ab174b42e26d2c2ee94`, `server/`.

This dedicated instance uses the same HMAC and provider-pull-v1 protocol, with
separate client/worker secrets, loopback port, persistent counters and SG worker.
The original education relay and its credentials remain independent.

The SG worker reaches the Ali loopback instance through a restricted SSH local
forward. Only the SG service reads `/root/.envs/default_apk` via systemd
LoadCredential; no OpenAI key is installed on Ali, Android or macOS.

## Dedicated meal-image instance

`food-start.cjs` reuses the unchanged vendor transport on Ali18781 with separate client/worker credentials, state and30/daybudget. The new SG worker uses `AI_RELAY_ORIGIN=http://127.0.0.1:18782` and `AI_RELAY_DAILY_LIMIT=30`; default values keep the original49/dayworker compatible. Poll job bodies are bounded to2MiB; provider replies stay256KiB. Non200 upstream replies are replaced with a static status code before relay caching, because provider errors can echo request details. Images remain only in the broker/worker process memory; only digests and small parsed responses enter application storage. The education relay and original analysis instance do not change. See [food/events contract](../../server/FOOD_EVENTS.md).
