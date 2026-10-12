# 复现 Windows 原生数据库/队列门禁（工程人员）

这是第一阶段隔离原型，**不是普通用户安装流程**；当前结论 NO-GO。
所有 fixture **SYNTHETIC ONLY / NOT A BENCHMARK**，不调用模型。实际结果见 [results](results.md)。

## 推荐复现

检出固定实现 `11e933bef82f1f71408447465c7dcd6a4d846157`，
参考 [完整 workflow](../../.github/workflows/native-feasibility.yml) 在 `windows-2025` x64 runner 执行。
workflow 实际测试 PG、编译扩展和 Garnet/RQ，无 Docker/WSL 命令。
后续修改原型文件并推送该独立分支会自动重新运行；原失败证据保持历史原状。

## 本机工程复现前提

Windows x64、Python3.11/uv0.12.19、匹配的 MSVC x64开发工具、PostgreSQL17的完整开发分发
（实际原型17.11，需bin/lib/share/include）。需要访问GitHub下载固定 Garnet ZIP和固定pgvector源码，
以及 locked uv 依赖。不要使用已有生产库，不要修改已安装PG的lib/share；不运行第三方安装脚本。
这些是工程复现依赖，不是预期最终用户的依赖。

在 MSVC x64 developer PowerShell 中，先检出上述 RAGSystem 实现；从官方
`https://github.com/pgvector/pgvector` 检出commit
`cab9da72c04353f143bb06b42ab70a403daac64a` 到独立路径。
以下示例替换仓库、源码和PG来源位置，路径必须是从未使用过的测试目录；程序会拒绝已有根目录。

```powershell
Set-Location 'C:\source\RAGSystem'
uv sync --locked
if ($LASTEXITCODE -ne 0) { throw 'locked dependencies failed' }
$probeId = [guid]::NewGuid().ToString('N')
$probeDataRoot = Join-Path $env:TEMP "RAG Native 中文 Path $probeId"
$probeRuntimeRoot = Join-Path $env:TEMP "rag-native-programs-$probeId"
# 要测试ASCII程序路径，确保 TEMP 本身为ASCII；不要修改全局用户环境。
uv run python scripts/native_probe/probe.py --prepare --workspace "$probeDataRoot" --runtime-root "$probeRuntimeRoot" --pg-source 'C:\Program Files\PostgreSQL\17'
if ($LASTEXITCODE -ne 0) { throw 'native preparation failed' }
$env:PGROOT = Join-Path $probeRuntimeRoot 'postgres'
Push-Location 'C:\source\pgvector'
try {
    nmake /F Makefile.win
    if ($LASTEXITCODE -ne 0) { throw 'pgvector build failed' }
    nmake /F Makefile.win install
    if ($LASTEXITCODE -ne 0) { throw 'pgvector copy install failed' }
} finally { Pop-Location }
uv run python scripts/native_probe/probe.py --workspace "$probeDataRoot" --output native-probe-report.json
$nativeGateExit = $LASTEXITCODE
Write-Host "Native gate exit: $nativeGateExit; inspect native-probe-report.json"
```

预期固定版本输出 `decision: NO_GO_PRODUCTION`，原型进程退出2；CI将其保留为失败门禁。
正常流程的PG/Garnet子进程关闭、密码临时文件移除；无现有用户数据清理。
若外部强行终止整个Python进程，仅定位此次 `$probeDataRoot` / `$probeRuntimeRoot` 的进程与文件，
不要全局杀postgres/Redis、删除卷或已有数据库；原型不是生产级退出管理器。

## 输入来源/运行资源（尚非最终安装器BOM）

| 输入与必要文件 | 来源/校验/分发状态 |
| --- | --- |
| postgres.exe/initdb.exe/pg_ctl.exe/createdb.exe/pg_dump.exe/pg_restore.exe/pg_config.exe，以及bin DLL、lib、share | Windows runner 的PG17.11完整开发分发副本，实际EXE哈希见报告；官方PG许可证宽松，但该分发第三方NOTICE/VC/OpenSSL/ICU等依赖闭环尚未完成，不能直接称为产品资源 |
| vector.dll、share/extension/vector.control、vector--*.sql | 上述官方pgvector v0.8.2源码/MSVC针对该PG17副本构建，PostgreSQL许可证；两runner实际vector.dll哈希独立记录 |
| GarnetServer.exe、程序集/runtime配置、native_device.dll、lua54.dll及同ZIP资源 | 官方v2.2.1 ZIP，50,818,670bytes，SHA256 `93f0026d305585cd249a91dda6fd44c46bcaa56304115b039f74f23fe630c64a`；源码MIT，[准确release源码/许可哈希](garnet-release-sources.json)已核验；完整资源依赖/第三方许可与无.NET开发环境验证尚未完成 |
| Python API/worker、Docling、模型缓存、业务配置、迁移 | 复用uv.lock和原代码；目前运行Python开发环境，**未冻结交付**，完整后端资源清单尚未完成 |
| 源码许可证/参考文件 | [reference-sources.json](reference-sources.json)固定commit、实际读取文件SHA与许可；不复制GPL/未授权代码 |

PG原型为发现真实依赖而复制完整开发目录，**没有证明这是最小包体**。
Garnet使用官方ZIP的net8.0主入口；服务wrapper的framework-dependent配置不等于主入口测试已证明
在无.NET/VC运行时的干净Windows11自包含。实际测试不安装或依赖Docker/WSL，但runner预装能力不能忽略。

不上传原始PG/Garnet/Worker日志、数据库、dump、私有配置、环境变量或密钥。
`native-probe-report.json`为安全结果，区分PASS/FAIL/NO_GO/NOT EXECUTED；不从它计算科研准确率。
