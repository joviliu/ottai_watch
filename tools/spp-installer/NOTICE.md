# Independent SPP development installer

This component is licensed AGPL-3.0; see LICENSE. It is an independent Android tool, separate from the GPL-3.0 blood-glucose mirror application.

The nine classes in `src/com/example/redmiwatch6installer/xiaomi/` come from:

- https://github.com/calinhoria/watchface-installer
- commit `7f22ace9cbafc72a8120ae9965ca04c961268048`
- The upstream author attributes the protocol implementation to Gadgetbridge (AGPLv3): XiaomiAuthService, XiaomiWatchfaceService, XiaomiDataUploadService, XiaomiSppPacketV1/V2, XiaomiFWHelper, XiaomiBitmapUtils and RedmiWatch6Coordinator.
- Local change: remove the generic raw connection log forwarding to Android logcat. The app ignores protocol diagnostic callbacks and reports only connection/authentication/install stages.

The original application's UI, preferences and embedded default pairing key were not copied. No third-party firmware, sample watchface or runtime credentials are included.

Bouncy Castle `bcprov-jdk18on:1.78.1` is fetched during build from Maven Central and SHA-256 pinned. Its permissive license is at https://www.bouncycastle.org/licence.html; its source is at https://github.com/bcgit/bc-java/tree/r1rv78 . The dependency is not committed to this repository.
