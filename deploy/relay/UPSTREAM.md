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
