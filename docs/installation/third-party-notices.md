# 第三方运行组件

Scientific RAGAgent源码为MIT。原生部署助手由未修改的PyInstaller6.16.0生成，使用其Bootloader Exception分发；已核查官方wheel的COPYING.txt，明确允许compiled bootloader与其他程序组合分发而不施加GPL限制。其runtime hooks为Apache2.0；Python为PSF许可证，可能包含OpenSSL（Apache2.0）。各组件保留自己的版权与许可，不因本项目MIT而重新授权。

- [PyInstaller许可及bootloader exception](https://pyinstaller.org/en/stable/license.html)
- [Python许可](https://docs.python.org/3/license.html)
- [OpenSSL许可](https://www.openssl.org/source/license.html)
- Docker Desktop有单独商业/订阅条款；不包含在客户端/部署助手中。
- PostgreSQL/pgvector、Redis7.4容器及模型权重由用户Docker/后端从上游下载，不把它们的源码或权重重新标为MIT。Redis7.4与各权重需遵守其独立许可。
- 既有Tauri/Rust/前端/Docling及模型许可证记录仍适用，见部署/依赖文档与ADR0008。

CI分发的是未签名测试构建，不是正式Release。
