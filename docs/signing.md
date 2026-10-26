# 签名与迁移

Android APK 与手表 RPK 必须使用相同包名 `com.example.glucosewatch6`、相同证书，否则互联通道不可用。

最初安装 0.1.4 的证书公开部分在 `signing/installed-certificate.pem`：

```
SHA-1   479a7dff09ae386146088e1fc78eeb1295b75c0e
SHA-256 462f0b0eaa5a1697edf85217e47c5eb96c17051fc47830641f781e37caff1b13
```

## 继续覆盖升级

从旧环境通过可信私密渠道迁移项目 `.sign/private.pem` 和 `.sign/certificate.pem` 到新环境的同名目录；私钥权限设为 `600`，再运行 `sh tools/prepare_signing.sh`，让手表构建使用同一证书。不要上传私钥、不要粘贴到聊天或 issue。

只迁移公开证书不能签名。仓库中的预编译安装包已经签好，可直接安装，不需要私钥。

## 新设备独立开发

没有原私钥时运行 `prepare_signing.sh` 会生成一套新签名。必须同时构建并安装新 APK 和新 RPK；不能覆盖旧签名应用。不要为尝试构建而卸载当前正常运行的应用。确需切换签名时，先记录配置；卸载手机应用会丢失其缓存和权限状态。

已知限制：当前脚本使用本地 PEM 签名，未集成云签名服务。公有 CI 仅运行不需要私钥的测试。
