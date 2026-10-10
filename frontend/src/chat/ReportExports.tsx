import { useEffect, useRef, useState } from "react";
import { downloadReport, type ExportFile } from "../transport";
import { errorMessage } from "../errors";

export function ReportExports({ runId }: { runId: string }) {
  const [format, setFormat] = useState<ExportFile>("report.md");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return (
    <div className="report-exports" aria-label="报告导出">
      <label>
        导出格式{" "}
        <select
          value={format}
          disabled={busy}
          onChange={(event) => setFormat(event.target.value as ExportFile)}
        >
          <option value="report.md">Markdown 报告</option>
          <option value="comparison.csv">比较表 CSV</option>
          <option value="references.bib">BibTeX 参考文献</option>
          <option value="citations.json">引用清单 JSON</option>
        </select>
      </label>{" "}
      <button
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setNotice("");
          setError("");
          void downloadReport(runId, format)
            .then((receipt) => {
              if (mounted.current)
                setNotice(
                  receipt.destination === "Downloads"
                    ? `已保存到系统下载目录：${receipt.filename}`
                    : `浏览器下载已发起：${receipt.filename}`,
                );
            })
            .catch((failure) => {
              if (mounted.current)
                setError(
                  errorMessage(
                    failure instanceof Error ? failure.message : failure,
                  ),
                );
            })
            .finally(() => {
              if (mounted.current) setBusy(false);
            });
        }}
      >
        {busy ? "正在导出…" : "导出当前结果"}
      </button>
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
