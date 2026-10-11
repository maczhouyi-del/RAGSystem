"""Windows graphical setup. No HTTP server, shell IPC or provider calls.

A single worker invokes the existing deployment API; Tk widgets stay on the UI
thread. Only static progress, presence booleans and safe codes reach the window.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Any

STEPS = ("检查安装条件", "连接本机授权", "安全保存密钥", "启动系统", "开始使用")
PROVIDERS = {
    "OpenAI": "OPENAI_API_KEY",
    "DeepSeek": "DEEPSEEK_API_KEY",
    "Anthropic": "ANTHROPIC_API_KEY",
    "本地模型 / 稍后配置": None,
}


def launch(deployment: Any, *, smoke: bool = False) -> bool:
    # Optional off Windows: the original console wizard is still supported.
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk

        from local_deploy import ADVICE

        root = tk.Tk()
    except Exception:
        # Imported lazily so CLI-only platforms do not need a GUI runtime.
        return False
    root.title("RAGSystem 安装与首次配置")
    root.geometry("820x620")
    root.minsize(740, 560)
    events: queue.Queue[tuple[str, Any]] = queue.Queue()
    deployment.progress = lambda text: events.put(("progress", text))
    state = {"step": 0, "busy": False, "checked": False, "started": False}
    presence = deployment.configuration_status()
    status = tk.StringVar(value="请先检查安装条件。助手不会自动调用模型或删除数据。")
    provider = tk.StringVar(value="OpenAI")
    verifier = tk.StringVar()
    key = tk.StringVar()
    resume = tk.BooleanVar(value=False)
    title = ttk.Label(root, font=("Segoe UI", 18, "bold"))
    title.pack(anchor="w", padx=24, pady=(20, 8))
    progress = ttk.Label(root)
    progress.pack(anchor="w", padx=24)
    content = ttk.Frame(root, padding=24)
    content.pack(fill="both", expand=True)
    status_box = ttk.Label(root, textvariable=status, wraplength=760)
    status_box.pack(anchor="w", padx=24, pady=12)
    spinner = ttk.Progressbar(root, mode="indeterminate")
    spinner.pack(fill="x", padx=24)
    footer = ttk.Frame(root, padding=20)
    footer.pack(fill="x")

    def note(text: str) -> None:
        ttk.Label(content, text=text, wraplength=740, justify="left").pack(anchor="w", pady=8)

    def action(text: str, callback: Callable[[], None]) -> None:
        ttk.Button(content, text=text, command=callback).pack(anchor="w", pady=10)

    def set_busy(value: bool) -> None:
        state["busy"] = value
        for frame in (content, footer):
            for widget in frame.winfo_children():
                if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Combobox, ttk.Checkbutton)):
                    widget.configure(
                        state="disabled"
                        if value
                        else ("readonly" if isinstance(widget, ttk.Combobox) else "normal")
                    )
        if value:
            spinner.start()
        else:
            spinner.stop()

    def run(work: Callable[[], None], success: str, *, marker: str | None = None) -> None:
        if state["busy"]:
            return
        set_busy(True)
        status.set("正在执行，请稍候…已有数据会保留。")

        def task() -> None:
            try:
                work()
                events.put(("done", (success, marker, deployment.configuration_status())))
            except Exception as error:
                # Exception text/SDK/subprocess output may contain private data.
                code = str(error) if type(error).__name__ == "DeployError" else "deployment_failed"
                events.put(("error", code if code in ADVICE else "deployment_failed"))

        threading.Thread(target=task, daemon=True).start()

    def check() -> None:
        state["checked"] = False

        def work() -> None:
            deployment.dependencies()
            deployment.progress("正在检查本机端口…")
            deployment.ports()

        run(
            work,
            ("安装条件通过。下一步连接桌面的本机授权；基础服务是否启动会在步骤4检查。"),
            marker="checked",
        )

    def pair() -> None:
        value = verifier.get().strip()
        if presence["paired"] and not value:
            move(1)
            return
        if presence["paired"] and not messagebox.askyesno(
            "确认更换本机配对",
            "已有配对将被替换，原桌面可能无法连接。确认这是你的桌面配对哈希？",
            parent=root,
        ):
            return
        run(
            lambda: deployment.pair(value),
            "配对已保存。没有保存桌面凭据明文；下一步安全保存模型密钥。",
        )

    def save_key() -> None:
        name = PROVIDERS[provider.get()]
        value = key.get()
        if name is None:
            key.set("")
            move(1)
            return
        if presence["keys"].get(name) and not messagebox.askyesno(
            "确认替换密钥", "此服务商已有私有密钥。确认替换？现有论文和会话会保留。", parent=root
        ):
            return
        key.set("")
        run(
            lambda: deployment.save_key(name, value),
            ("密钥已私密保存；尚未验证有效性。点击下一步启动系统，再回到桌面选择服务商和模型。"),
        )

    def start() -> None:
        if not resume.get():
            status.set(
                "请先确认：启动会恢复已有排队任务，其模型调用可能收费。新安装不会自动发起模型测试。"
            )
            return
        run(
            deployment.start, "系统已就绪。点击下一步，回到桌面完成模型快捷配置。", marker="started"
        )

    def move(delta: int) -> None:
        if state["busy"]:
            return
        if delta > 0 and state["step"] == 0 and not state["checked"]:
            status.set("请先点击检查安装条件；失败后按提示处理并重新检查。")
            return
        if delta > 0 and state["step"] == 1 and not presence["paired"]:
            status.set("请先保存配对哈希。此操作保持本机身份认证，不能跳过。")
            return
        if delta > 0 and state["step"] == 3 and not state["started"]:
            status.set("请先启动系统并等待就绪；失败可直接点击启动/恢复重试。")
            return
        key.set("")
        state["step"] = max(0, min(len(STEPS) - 1, state["step"] + delta))
        render()

    def render() -> None:
        for widget in content.winfo_children() + footer.winfo_children():
            widget.destroy()
        step = state["step"]
        title.configure(text=STEPS[step])
        progress.configure(text=f"步骤 {step + 1} / {len(STEPS)}  ·  " + " → ".join(STEPS))
        if step == 0:
            note(
                "桌面安装包需配合部署 ZIP 和 Docker。助手会检查 Do"
                "cker、WSL（适用时）、版本、磁盘及端口；你无需编辑配置文件"
                "或执行部署命令。"
            )
            note(
                "先安装并启动 Docker Desktop，Windows 需使"
                "用 Linux containers。建议 16 GB 内存、至"
                "少 20 GiB 可用空间；第一次构建需要互联网。"
            )
            note(
                "已有安装已识别，原论文、索引、会话和私有配置会保留。"
                if presence["existing"]
                else ("未发现本目录的安装配置。请使用已核对校验值的部署 ZIP，并保留此目录。")
            )
            action("检查安装条件 / 重新检查", check)
            if presence["paired"]:

                def existing_start() -> None:
                    state["step"] = 3
                    render()

                action("使用已有配置启动 / 恢复", existing_start)
        elif step == 1:
            note(
                "打开桌面程序 → 连接授权 → 复制配对哈希，粘贴到这里。只需复"
                "制一次；它不是 API Key，也不是桌面凭据明文。"
            )
            if presence["paired"]:
                note("已有本机配对已识别。无需重复配对，直接下一步；只有更换桌面时才填写新哈希。")
            ttk.Label(content, text="桌面配对哈希（64个小写十六进制字符）").pack(anchor="w")
            ttk.Entry(content, textvariable=verifier, width=76).pack(fill="x", pady=8)
            action("保存配对哈希", pair)
        elif step == 2:
            note(
                "选择服务商并隐藏输入 API Key。密钥只写入本机私有运行时文"
                "件，不会发送给前端、日志或报告。保存不代表密钥有效，也不会调用模"
                "型。"
            )
            ttk.Combobox(
                content, textvariable=provider, values=list(PROVIDERS), state="readonly"
            ).pack(anchor="w", pady=8)
            existing = [
                label for label, name in PROVIDERS.items() if name and presence["keys"].get(name)
            ]
            note(
                "已有密钥："
                + ("、".join(existing) if existing else "未配置")
                + "。已有密钥可直接保留并下一步。"
            )
            ttk.Label(content, text="API Key（隐藏输入）").pack(anchor="w")
            ttk.Entry(content, textvariable=key, show="●", width=70).pack(fill="x", pady=8)
            action("安全保存密钥", save_key)
            note(
                "本地模型或暂未备妥密钥：可以点击下一步，稍后回来配置。桌面 Se"
                "ttings 会明确显示密钥是否存在；不会将未配置状态记为成功。"
            )
        elif step == 3:
            note(
                "点击后自动启动后台系统并初始化数据库，首次约 10–30 分钟。"
                "窗口仍可显示进度；若失败，按提示处理后点击同一按钮重试。不会清理"
                "已有数据。"
            )
            ttk.Checkbutton(
                content,
                variable=resume,
                text="我了解启动可能恢复已有排队任务，其模型调用可能产生费用",
            ).pack(anchor="w", pady=10)
            action("启动 / 恢复系统", start)
        else:
            note(
                (
                    "基础服务已就绪。"
                    if state["started"]
                    else "系统已停止或尚未启动，请回到步骤4启动。"
                )
                + "回到桌面程序 → 连接授权 → 连接并检查授权，"
                "然后按首次使用引导选择服务商和聊天模型。四个角色可使用同一默认模"
                "型，高级设置仍可单独修改。"
            )
            note(
                "随后导入第一篇 PDF，等待文献列表显示 indexed，再发起"
                "第一次问答。远程模型可能收费；本地模型首次下载可能耗时，网络失败"
                "可按故障排查恢复。"
            )
            note(
                "关闭桌面不会自动停止后台系统。需要停止时点击下方按钮；论文、会话"
                "、配置和数据卷全部保留。备份、升级、恢复及保留数据卸载仍可用独立"
                "助手 --console。"
            )
            action(
                "停止系统（保留所有数据）",
                lambda: run(
                    deployment.stop,
                    "系统已停止，所有用户数据保留。重新启动请回到步骤4。",
                    marker="stopped",
                ),
            )
        if step > 0:
            ttk.Button(footer, text="上一步", command=lambda: move(-1)).pack(side="left")
        if step < len(STEPS) - 1:
            ttk.Button(footer, text="下一步", command=lambda: move(1)).pack(side="right")
        else:
            ttk.Button(footer, text="完成 / 返回桌面", command=root.destroy).pack(side="right")

    def poll() -> None:
        nonlocal presence
        try:
            while True:
                kind, data = events.get_nowait()
                if kind == "progress":
                    status.set(data)
                elif kind == "error":
                    set_busy(False)
                    status.set(ADVICE[data] + "  安全错误码：" + data)
                else:
                    message, marker, presence = data
                    if marker:
                        state[marker] = True
                    if marker == "stopped":
                        state["started"] = False
                    render()
                    set_busy(False)
                    status.set(message)
        except queue.Empty:
            pass
        root.after(100, poll)

    def close() -> None:
        if state["busy"]:
            messagebox.showinfo(
                "操作正在进行",
                (
                    "请等待当前操作完成。首次构建可能需要 10–30 分钟；不要强制"
                    "退出或清理 Docker 数据。"
                ),
                parent=root,
            )
        else:
            key.set("")
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    render()
    smoke_finished = False
    poll()
    if smoke:
        assert state["step"] == 0 and not state["busy"]
        # Actual native Tk widgets with explicit MOCK error/retry jobs. No
        # Docker, inference or file writes; this is not human OS acceptance.
        before = deployment.configuration_status()
        for step in range(len(STEPS)):
            state["step"] = step
            render()
            root.update_idletasks()
            if step == 2:
                entries = [
                    w
                    for w in content.winfo_children()
                    if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)
                ]
                assert len(entries) == 1 and entries[0].cget("show")
        state["step"] = 0
        render()

        def mock_failure() -> None:
            from local_deploy import DeployError

            raise DeployError("docker_missing")

        def verify_retry() -> None:
            nonlocal smoke_finished
            if state["busy"]:
                root.after(50, verify_retry)
                return
            smoke_finished = (
                status.get() == "MOCK UI retry passed"
                and deployment.configuration_status() == before
            )
            root.destroy()

        def verify_error() -> None:
            if state["busy"]:
                root.after(50, verify_error)
                return
            assert "docker_missing" in status.get()
            assert deployment.configuration_status() == before
            run(lambda: None, "MOCK UI retry passed")
            root.after(50, verify_retry)

        run(mock_failure, "Unexpected success")
        assert state["busy"]
        assert all(
            str(w.cget("state")) == "disabled"
            for w in content.winfo_children()
            if isinstance(w, ttk.Button)
        )
        root.after(50, verify_error)
        root.after(10000, root.destroy)
    root.mainloop()
    if smoke:
        assert smoke_finished, "Native GUI MOCK safety smoke did not complete"
        print(
            "PASS: native GUI five pages rendered; MOCK error/retry and masked key "
            "checked; no Docker/model calls or data writes."
        )

    return True
