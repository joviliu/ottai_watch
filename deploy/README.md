# 已部署服务的接续

当前为两个隔离服务面：Ali保存和统计单个成年使用者的授权资料；SG通过独立隧道取任务，只有SG读取提供方API key。原教育项目的API、relay、worker及密钥保持独立。此目录模板不含秘密；完整数据契约和验收状态见[接续](../docs/CLOUD_SYNC_HANDOFF.md)。

## 路径与启动

Ali：`server/`放在`/srv/ottai-cloud/app/server`，API/日报模板在`server/deploy`。用户`ottai-cloud`拥有`/var/lib/ottai-cloud`（0700），root的`/etc/ottai-cloud/service.env`（0600）定义独立读/写token、DB路径和relay业务身份。API仅监听127.0.0.1:18776。备份脚本在`/srv/ottai-cloud/app/deploy/backup.py`，复制本目录的备份unit/timer。

专用relay代码在`/opt/ottai-cloud/deploy/relay`，用户`ottai-relay`只可写`/var/lib/ottai-relay`。配置位于`/etc/ottai-relay/relay.env`及`clients.json`：使用vendor模块的`OPENAI_RELAY_CLIENTS_FILE`、`OPENAI_RELAY_STATE_DIR`和`AI_RELAY_SECRET`等配置名；必须提供独立HMAC密钥和ottai业务配置，不能复用教育业务凭据。该业务`dailyLimit=1`，全局上限2。当前Node可执行路径写在`ottai-relay.service`，新环境核对实际安装路径后再部署。

SG：`worker.py`放在`/opt/ottai-ai`，用户`ottai-ai`只可写`/var/lib/ottai-ai`。root的`/etc/ottai-ai/worker.env`（0600）定义`AI_RELAY_SECRET`、`AI_WORKER_ID`和`AI_RELAY_STATE_DIR`，与独立relay配对；OpenAI key通过unit的`LoadCredential`读取所有者指定的源文件。不能把key复制到Ali或客户端。worker只接受固定Responses路径、`store:false`、非stream/background请求，预留请求身份后不重试未知执行结果。

SG的`ottai-ai-tunnel.service`将本地127.0.0.1:18778转到Ali的127.0.0.1:18779。独立SSH私钥放SG`/etc/ottai-ai/id_ed25519`（0600），核对主机指纹后写`known_hosts`。Ali专用用户`ottai-tunnel`的authorized_keys使用`restrict,port-forwarding,permitopen="127.0.0.1:18779",command="/bin/false"`，只允许这一转发，不开放shell或复用管理员私钥。

## HTTPS与既有服务

现有8443代理通过systemd drop-in改用`/opt/ottai-cloud/deploy/https-router.cjs`，只新增`/ottai/`→18776并移除前缀；其他路径继续发原18766。TLS目录和证书续期/SIGHUP重载保持原配置。新环境可改用`server/deploy/nginx-location.example`接入自己的有效HTTPS。不要在缺少原服务上下文时直接覆盖别人的代理unit或证书。

更改后执行适当的`systemctl daemon-reload`，启用API、relay、SG隧道/worker及日报/备份timer。检查各服务active、public`/ottai/health`、独立read token查询、read token写入被拒绝、原教育`/api/health`仍成功。不得把临时合成健康点写进正式数据库以通过72h门槛。

## 备份恢复与继续验证

`backup.py`通过SQLite读事务导出一致gzip SQL快照，兼容Ali的Python3.6，保留14份。恢复时将gzip内容交给隔离SQLite库的`executescript`，核对表、记录数和首末源身份后删除该临时恢复库；不要覆盖运行中的正式库。快照仍含完整健康资料，只保存在私密目录。

迁移前用所有者控制的安全通道迁移必要的服务配置、DB一致快照及签名，重新确认客户端身份。不能随意生成新token后假定旧设备会匹配；也不能将真实env、数据库或凭据提交Git。重建服务的技术步骤不等于真实跨日分析、自然timer或长期恢复已验证。
