import { useEffect, useRef, useState } from "react";
import { Event, Run, api } from "../api";
import type { Event as EventType, Message, Run as RunType } from "../api";
import { stream } from "../transport";
import { activeStatus } from "./useConversationMessages";

/** SSE owns live progress; disconnected reconciliation is bounded and stops on reconnect. */
export function useRunEvents(
  message: Message,
  details: boolean,
  onReconcile: (messageId: string) => Promise<void>,
) {
  const revision = `${message.run_id}:${message.updated_at}`;
  const latestRevision = useRef(revision);
  latestRevision.current = revision;
  const [detail, setDetail] = useState<{
    revision: string;
    run: RunType;
  } | null>(null);
  const fullRun = detail?.revision === revision ? detail.run : null;
  const [eventState, setEvents] = useState<{
    revision: string;
    items: (EventType & { eventId: string })[];
  }>({ revision, items: [] });
  const events = eventState.revision === revision ? eventState.items : [];
  const [connection, setConnection] = useState("");
  const cursor = useRef(0);
  const callback = useRef(onReconcile);
  callback.current = onReconcile;
  const pendingDetail = useRef<{
    revision: string;
    promise: Promise<RunType>;
    controller: AbortController;
  } | null>(null);
  const full = useRef(fullRun);
  full.current = fullRun;
  const runId = message.run_id;
  const running = activeStatus(message.status);
  const loadRun = async (fresh = false) => {
    if (!fresh && full.current && !activeStatus(full.current.status))
      return full.current;
    if (!runId) throw new Error("run_not_found");
    if (pendingDetail.current?.revision !== revision) {
      pendingDetail.current?.controller.abort();
      pendingDetail.current = null;
    }
    if (!pendingDetail.current) {
      const controller = new AbortController();
      const promise = api(
        `/api/runs/${runId}`,
        Run,
        undefined,
        "GET",
        AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]),
      )
        .then((run) => {
          if (latestRevision.current !== revision || controller.signal.aborted)
            throw new DOMException("Source revision changed", "AbortError");
          full.current = run;
          setDetail({ revision, run });
          return run;
        })
        .finally(() => {
          if (pendingDetail.current?.promise === promise)
            pendingDetail.current = null;
        });
      pendingDetail.current = { revision, promise, controller };
    }
    return pendingDetail.current.promise;
  };

  useEffect(() => {
    cursor.current = 0;
    setEvents({ revision, items: [] });
    setConnection("");
    setDetail(null);
    return () => {
      pendingDetail.current?.controller.abort();
      pendingDetail.current = null;
    };
  }, [revision]);
  useEffect(() => {
    if (!runId || (!running && !details)) {
      setConnection("");
      return;
    }
    let live = true;
    let attempts = 0;
    let recovery: ReturnType<typeof setTimeout> | undefined;
    const stopRecovery = () => {
      clearTimeout(recovery);
      recovery = undefined;
      attempts = 0;
    };
    const scheduleRecovery = () => {
      if (!live || recovery || attempts >= 6) return;
      recovery = setTimeout(
        () => {
          recovery = undefined;
          attempts += 1;
          void callback
            .current(message.id)
            .catch(() => undefined)
            .finally(() => {
              if (live) scheduleRecovery();
            });
        },
        Math.min(1000 * 2 ** attempts, 10000),
      );
    };
    const close = stream(`/api/runs/${runId}/events`, {
      cursor: cursor.current,
      onOpen: () => {
        if (live) {
          stopRecovery();
          setConnection("");
        }
      },
      onExecution: (data, eventId) => {
        if (!live || latestRevision.current !== revision) return;
        try {
          const parsed = Event.parse(JSON.parse(data));
          const next = Number(eventId);
          if (eventId && Number.isFinite(next) && next <= cursor.current)
            return;
          if (eventId && Number.isFinite(next)) cursor.current = next;
          stopRecovery();
          setConnection("");
          setEvents((previous) => ({
            revision,
            items: [
              ...(previous.revision === revision ? previous.items : []),
              { ...parsed, eventId },
            ],
          }));
        } catch {
          setConnection("执行事件格式错误，正在从数据库恢复状态。");
          scheduleRecovery();
        }
      },
      onDone: (data) => {
        if (!live || latestRevision.current !== revision) return;
        stopRecovery();
        try {
          const run = Run.parse(JSON.parse(data));
          setDetail({ revision, run });
          full.current = run;
          setConnection("");
        } catch {
          setConnection("结果格式错误，正在从数据库恢复状态。");
        }
        void callback.current(message.id).catch(() => {
          if (live) {
            setConnection("正在从数据库恢复最终状态。");
            scheduleRecovery();
          }
        });
      },
      onError: () => {
        if (live) {
          setConnection("事件连接中断，正在重连；后台任务继续执行。");
          scheduleRecovery();
        }
      },
    });
    return () => {
      live = false;
      stopRecovery();
      close();
    };
  }, [runId, running, details, message.id, revision]);
  return { fullRun, events, connection, loadRun };
}
