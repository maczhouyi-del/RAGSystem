# 数据、备份、升级与卸载

程序文件、部署目录和用户数据是三部分。桌面程序安装在 OS 应用目录；部署目录包含锁定源文件、Compose、助手与两个私有 runtime 环境文件。
核心数据在 Docker named volumes：`scientific-ragagent_postgres`（元数据/向量/会话/Run/迁移）、`_papers`（PDF）、`_config`（角色配置）、`_redis`（队列）、`_models`（模型缓存）。
Docker Desktop 内部虚拟磁盘由 Docker 管理；Linux 可通过 Docker volume inspect 查询，**不要直接编辑数据库文件**。
客户端 bearer 在 OS 密钥库，Web bearer 只在页面内存。

## 备份

等待导入、问答、Research、评测全部完成，再在助手选择 **6 备份**。
选择部署目录外的长期位置；助手暂停 API/worker/Web，使用 PostgreSQL17 `pg_dump -Fc` 和 PDF/config tar，
保存非敏感 runtime 设置、实际文件 SHA256 与格式元数据，最后恢复原服务，不在备份时构建/迁移新版本。
活跃任务会拒绝备份；失败备份缺少完整 manifest，不能用于升级。输出为敏感科研数据，保存在当前用户私有权限目录。
不要使用 Docker Desktop Delete volumes / Clean/Purge data。备份后不要移动或清理原卷来“验证”。

API 密钥、DB密码、bearer、Redis队列与模型权重缓存**不包含在备份**。私有 `.runtime-secrets.env`、旧 `.env` 和 OS 配对凭据需要保留在原电脑；
异机恢复时重新输入获准 API 密钥、重新配对、重新下载固定版本模型，不能从报告中还原密钥。
配置中如含用户自行添加的敏感 endpoint/query，应自行检查非敏感设置表；不要共享备份。

## 升级

先用当前/新助手做一次完整备份，保留备份 manifest 和原私有 runtime 文件，再安装对应平台新客户端。
新部署 ZIP 解压到**临时目录**核对 SHA/manifest，将源文件、Compose、助手、文档更新到原部署目录；
不要覆盖 `.env`、`.runtime-secrets.env`，不要改变项目名或删除 named volumes。
使用助手 **7 升级**：再次备份成功之后才允许构建镜像/启动并执行原 Alembic 迁移。
无备份、活跃任务或 dump 失败时停止升级。失败保留原数据和失败记录，请按故障排查恢复；不自动降级数据库。

测试版支持 PostgreSQL17 内同项目升级。PostgreSQL 主版本切换必须先单独设计/测试 export/restore，不能仅改镜像 tag。
模型/向量维度更换按已有索引兼容性规则进行，助手不自动重建或删除旧索引。

## 在空白 Docker 环境恢复

仅使用自己的、完整且可信的备份；SQL/tar 备份不是不可信交换格式。
部署助手只允许在该项目的五个 named volumes **全部不存在**时恢复，拒绝覆盖任何已有用户数据。
在新电脑装好 Docker，解压对应部署 ZIP，运行一次：

```text
RAGSystem-Setup restore --backup-directory 备份目录 --confirm-empty-restore
```

Windows 使用 `RAGSystem-Setup.exe`，Unix 使用 `./RAGSystem-Setup`。
核对文件 SHA256 后，创建新 DB/Redis 卷、恢复数据库/PDF/config 与非敏感设置。
再打开桌面重新配对、重新输入私有 API 密钥、选择启动。
恢复失败时已经创建的卷会保留；不要删除旧数据或强制覆盖以绕过空白检查，寻求维护帮助。
自动化工程测试会恢复到一个独立空项目，并核对原 PDF、配置和运行历史；不代表用户异机人工验收。

## 卸载

卸载桌面 MSI/NSIS/应用只移除应用程序文件，Docker 后端仍独立运行。需要停止时用助手 **4 停止**。
选择助手 **8 卸载容器**并明确输入 KEEP DATA，只执行 Docker Compose down，不带 `-v`，
数据库/PDF/索引/会话/config/models 卷、部署目录私有文件、OS 配对凭据全部保留。
以后重新安装客户端并从同一项目启动可以恢复数据。助手没有全数据擦除命令。
主动完整删除数据必须由用户另行明确管理、先备份并理解不可逆影响；本文不把它作为普通卸载步骤。
