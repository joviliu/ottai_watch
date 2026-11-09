# Lua precision-test sources

Unmodified official release archives, used only to compile the float32 Lua5.2 and int32 Lua5.3 executables for CI's palette regression checks. Keeping these small fixed inputs avoids a runtime dependency on the upstream site's TLS availability. CI still verifies the same pinned SHA256 before unpacking and running the existing test.

| Archive | Official source | SHA256 |
| --- | --- | --- |
| lua-5.2.4.tar.gz | https://www.lua.org/ftp/lua-5.2.4.tar.gz | b9e2e4aad6789b3b63a056d442f7b39f0ecfca3ae0f1fc0ae4e9614401b69f4b |
| lua-5.3.6.tar.gz | https://www.lua.org/ftp/lua-5.3.6.tar.gz | fc5fd69bb8736323f026672b1b7235da613d7177e72558893a0bdcd320466d60 |

Lua is distributed under the MIT license; copyright and license are included in each unmodified archive (README/doc). No prebuilt executables or task credentials are included here.
