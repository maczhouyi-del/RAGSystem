# ADR-0008: Desktop installer and managed local Docker deployment

Status: accepted for TASK-18 implementation, 2026-10-10 (user-authorized order correction).

The Tauri MSI/NSIS is a client, not a complete research installation. PostgreSQL/pgvector, Redis, API, three RQ workers, Docling, embedding/reranking libraries and persistent configuration must run separately. Preserve the existing architecture and all TASK-00–16 behavior.

| Concern | A: desktop + automated Docker backend | B: embed Python, workers, PostgreSQL and Redis in installer |
| --- | --- | --- |
| Ordinary-user setup | Install Docker Desktop (Windows/macOS) or Engine + Compose (Linux); supplied native setup assistant handles deployment. No developer toolchain. | Fewer visible dependencies, but new DB/service installers, privileges and background process lifecycle on each OS. |
| Maintenance | Reuse pinned Compose, migration, workers and existing CI. Small stdlib assistant invokes fixed Docker operations. | Maintain three platform service managers and native PG/Redis/Docling distribution, in addition to Tauri. |
| Database upgrades | Stable project/volume identities; quiesced backups and explicit migration. Major PG upgrades remain manual/export-restore. | Same DB upgrade risks plus installer-owned service paths and OS privilege differences. |
| Data/security | Loopback API/Web; no public PG/Redis; runtime keys outside artifacts; explicit backups; no volume removal. Docker access is privileged, only trusted assistant/packages. | New privilege boundaries, antivirus/signing and uninstall hazards; no automatic advantage for data safety. |
| Size | Small client/assistant, multi-GB backend image + independently downloaded model caches. Internet required for first build/download. | Multi-GB installers per architecture; independently licensed weights still required. |
| Platforms | Existing Linux containers; native client/assistant Windows x64, macOS arm64/x64, Linux x64. | Python/PG/Redis native distributions and numerical wheels for every architecture; Windows Redis support is additional infrastructure. |

Choose A. Provide a versioned deployment ZIP containing a native assistant and a whitelist of locked source/build inputs. The assistant never requires host Python/Node/Rust. Use Docker's existing context without silently installing Docker, WSL, changing security policy or terminating unrelated processes. Fixed default ports 8000/8080 remain because the restricted desktop bridge expects them; conflicts produce actionable errors, never kill processes or silently connect to a different API.

Stable Compose project `scientific-ragagent` and named postgres/redis/papers/models/config volumes remain unchanged. No down -v, volume prune, automatic data removal, implicit restore or major database upgrade. Backup quiesces writers and preserves DB/PDF/config; credentials remain a separately protected local runtime file and are excluded from backup/export. Backup is sensitive scientific data. Preserve existing volumes and .env on upgrades; require a successful backup before migration. Uninstall stops/removes containers only on explicit action, retaining all volumes, configuration and pairing credentials; full data erasure is outside the assistant.

Runtime API keys use a permission-restricted local runtime environment file, never provider configuration values, database, package, command-line arguments or logs. Desktop pairing remains OS credential storage + nonsecret SHA256 verifier. Browser pairing stays its existing local flow. No provider calls in automatic setup; inference tests are explicit and can incur fees. MOCK engineering tests remain separate from real scientific acceptance.

Native assistant packaging uses PyInstaller 6.16.0 as a build tool only. Upstream GPL-2.0 bootloader exception explicitly permits distribution of generated executables under the application's license (https://pyinstaller.org/en/stable/license.html). No GPL project source is copied into this MIT repository. Docker Desktop has separate licensing/subscription requirements; Redis 7.4 and model weights retain their upstream licenses. The installer does not redistribute a Docker daemon or vendor Redis/weights; user Docker pulls the existing pinned images. Preserve existing dependency locks; review any new models before downloading.

Unsigned CI artifacts are test builds, not signed/notarized releases. Native CI proves the specific runner/architecture build/tests, not human installation on Windows 11/macOS. Record unexecuted platforms, architecture tests, first-user installation and real scientific metrics honestly.
