import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";
import { Collection, CollectionPage, api } from "./api";
import type { Filters } from "./components";

const labels = { group: "分组", tag: "标签" };
export function useCollections() {
  const [items, setItems] = useState<Collection[]>([]),
    [total, setTotal] = useState<number | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const current = useRef(items);
  current.current = items;
  const sequence = useRef(0),
    active = useRef(false),
    alive = useRef(true),
    controller = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      alive.current = false;
      controller.current?.abort();
    },
    [],
  );
  const load = useCallback(async (more = false, force = false) => {
    if (active.current && !force) return;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    const version = ++sequence.current;
    active.current = true;
    setBusy(true);
    setError("");
    try {
      const page = await api(
        `/api/collections?limit=200&offset=${more ? current.current.length : 0}`,
        CollectionPage,
        undefined,
        "GET",
        AbortSignal.any([request.signal, AbortSignal.timeout(10000)]),
      );
      if (!alive.current || version !== sequence.current) return;
      setItems(
        more
          ? [
              ...new Map(
                [...current.current, ...page.items].map((c) => [c.id, c]),
              ).values(),
            ]
          : page.items,
      );
      setTotal(page.total);
    } catch (failure) {
      if (alive.current && version === sequence.current)
        setError(String(failure));
    } finally {
      if (alive.current && version === sequence.current) {
        active.current = false;
        setBusy(false);
      }
    }
  }, []);
  return { items, total, busy, error, load, reload: () => load(false, true) };
}
type Catalog = ReturnType<typeof useCollections>;
export function CollectionOptions({
  items,
  kind,
  selected,
}: {
  items: Collection[];
  kind: Collection["kind"];
  selected: string[];
}) {
  const values = items.filter((c) => c.kind === kind);
  return (
    <>
      {values.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
      {selected
        .filter((id) => !values.some((c) => c.id === id))
        .map((id) => (
          <option key={id} value={id}>
            已选范围（未读取或已删除）：{id}
          </option>
        ))}
    </>
  );
}
function CatalogControls({ catalog }: { catalog: Catalog }) {
  return (
    <>
      <button
        type="button"
        disabled={catalog.busy}
        onClick={() => void catalog.reload()}
      >
        刷新分组与标签
      </button>
      {catalog.total !== null && catalog.items.length < catalog.total && (
        <button
          type="button"
          disabled={catalog.busy}
          onClick={() => void catalog.load(true)}
        >
          加载更多分组与标签
        </button>
      )}
      {catalog.busy && <p role="status">正在读取分组与标签…</p>}
      {catalog.error && <p role="alert">{catalog.error}</p>}
    </>
  );
}
export function OrganizationFilters({
  value,
  onChange,
}: {
  value: Filters;
  onChange: (v: Filters) => void;
}) {
  const catalog = useCollections();
  return (
    <div aria-label="科研项目检索范围">
      <p>
        同字段多个分组或标签取并集；分组、标签和其他条件取交集。未知或已删除 ID
        仍限制范围，不会自动扩大到全库。
      </p>
      <div className="grid">
        {(["group", "tag"] as const).map((kind) => {
          const key = kind === "group" ? "group_ids" : "tag_ids";
          return (
            <div key={kind}>
              <label>
                {labels[kind]}检索范围（可多选）
                <select
                  aria-label={`${labels[kind]}检索范围（可多选）`}
                  multiple
                  size={3}
                  value={value[key] ?? []}
                  onFocus={() => void catalog.load()}
                  onChange={(event) =>
                    onChange({
                      ...value,
                      [key]: Array.from(event.target.selectedOptions).map(
                        (o) => o.value,
                      ),
                    })
                  }
                >
                  <CollectionOptions
                    items={catalog.items}
                    kind={kind}
                    selected={value[key] ?? []}
                  />
                </select>
              </label>
              <button
                type="button"
                onClick={() => onChange({ ...value, [key]: [] })}
              >
                清除{labels[kind]}范围
              </button>
            </div>
          );
        })}
      </div>
      <CatalogControls catalog={catalog} />
    </div>
  );
}
function DeleteCollection({
  collection,
  onClose,
  onDeleted,
}: {
  collection: Collection;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null),
    lock = useRef(false),
    alive = useRef(true);
  const [verified, setVerified] = useState(true);
  const [current, setCurrent] = useState(collection),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
    return () => {
      alive.current = false;
    };
  }, []);
  async function remove() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await api(
        `/api/collections/${current.id}`,
        z.unknown(),
        {
          confirm_collection_id: current.id,
          expected_version: current.version,
        },
        "DELETE",
        AbortSignal.timeout(30000),
      );
      if (alive.current) onDeleted();
    } catch (failure) {
      setVerified(false);
      // Ambiguous writes recover through a read, never automatic DELETE replay.
      try {
        const latest = await api(
          `/api/collections/${current.id}`,
          Collection,
          undefined,
          "GET",
          AbortSignal.timeout(10000),
        );
        if (alive.current) {
          setCurrent(latest);
          setVerified(true);
          setError(`请核对最新名称和版本后再确认。${String(failure)}`);
        }
      } catch (readFailure) {
        if (!alive.current) return;
        if (String(readFailure).includes("collection_not_found")) onDeleted();
        else
          setError(
            `操作结果待核对，请关闭并刷新后重新确认。${String(readFailure)}`,
          );
      }
    } finally {
      lock.current = false;
      if (alive.current) setBusy(false);
    }
  }
  return (
    <dialog
      className="collection-confirmation"
      ref={dialog}
      aria-label="删除分组或标签确认"
      onCancel={(e) => {
        if (lock.current) e.preventDefault();
        else onClose();
      }}
    >
      <h3>
        删除{labels[current.kind]}：{current.name}
      </h3>
      <p>
        仅删除这个{labels[current.kind]}及其论文关联。论文、PDF、向量和已有
        Evidence 会保留。使用这个 ID 的检索范围会变为空范围，请明确重新选择。
      </p>
      <p>
        当前名称版本：{current.version}；关联 {current.paper_count} 篇论文。
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="inline">
        <button disabled={busy} onClick={onClose}>
          取消
        </button>
        <button
          className="danger"
          disabled={busy || !verified}
          onClick={() => void remove()}
        >
          {busy ? "正在删除…" : "确认仅删除分组或标签"}
        </button>
      </div>
    </dialog>
  );
}
export function CollectionManager({
  catalog,
  onChanged,
}: {
  catalog: Catalog;
  onChanged: () => void;
}) {
  const [name, setName] = useState(""),
    [kind, setKind] = useState<Collection["kind"]>("group"),
    [drafts, setDrafts] = useState<Record<string, string>>({});
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [deleting, setDeleting] = useState<Collection | null>(null);
  const lock = useRef(false),
    alive = useRef(true);
  useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );
  async function save(item?: Collection) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api(
        item ? `/api/collections/${item.id}` : "/api/collections",
        Collection,
        item
          ? {
              name: drafts[item.id] ?? item.name,
              expected_version: item.version,
            }
          : { name, kind },
        item ? "PATCH" : "POST",
        AbortSignal.timeout(30000),
      );
      if (!alive.current) return;
      if (item)
        setDrafts((values) => {
          const next = { ...values };
          delete next[item.id];
          return next;
        });
      else setName("");
      setNotice(`${labels[result.kind]} ${result.name} 已保存`);
      onChanged();
    } catch (failure) {
      if (alive.current) setError(String(failure));
    } finally {
      lock.current = false;
      if (alive.current) {
        setBusy(false);
        await catalog.reload();
      }
    }
  }
  return (
    <details
      aria-label="分组与标签管理"
      onToggle={(e) => {
        if (e.currentTarget.open) void catalog.load();
      }}
    >
      <summary>管理论文分组与标签</summary>
      <p>
        一篇论文可属于多个分组和标签。组织操作不复制 PDF
        或向量，也不改变科研证据。
      </p>
      <form
        aria-label="创建分组或标签"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
        className="inline"
      >
        <label>
          组织类型
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as Collection["kind"])}
          >
            <option value="group">分组</option>
            <option value="tag">标签</option>
          </select>
        </label>
        <label>
          分组或标签名称
          <input
            maxLength={80}
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <button disabled={busy || !name.trim() || deleting !== null}>
          创建
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <CatalogControls catalog={catalog} />
      {catalog.total === 0 && <p>尚无分组或标签。</p>}
      <ul className="collection-list">
        {catalog.items.map((item) => (
          <li key={item.id}>
            <span>
              {labels[item.kind]}：{item.name} · {item.paper_count} 篇
            </span>
            <label>
              修改 {item.name} 名称
              <input
                maxLength={80}
                value={drafts[item.id] ?? item.name}
                onChange={(e) =>
                  setDrafts((v) => ({ ...v, [item.id]: e.target.value }))
                }
              />
            </label>
            <button
              aria-label={`重命名${labels[item.kind]} ${item.name}`}
              disabled={
                busy ||
                deleting !== null ||
                !(drafts[item.id] ?? item.name).trim() ||
                (drafts[item.id] ?? item.name) === item.name
              }
              onClick={() => void save(item)}
            >
              保存名称
            </button>
            <button
              aria-label={`删除${labels[item.kind]} ${item.name}`}
              disabled={busy || deleting !== null}
              onClick={() => setDeleting(item)}
            >
              删除{labels[item.kind]}
            </button>
          </li>
        ))}
      </ul>
      {deleting && (
        <DeleteCollection
          key={deleting.id}
          collection={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setDeleting(null);
            void catalog.reload();
            onChanged();
          }}
        />
      )}
    </details>
  );
}
export function PaperOrganization({
  paper,
  catalog,
  disabled,
  onChanged,
}: {
  paper: { id: string; title: string };
  catalog: Catalog;
  disabled: boolean;
  onChanged: () => void;
}) {
  const details = useRef<HTMLDetailsElement>(null);
  const [pending, setPending] = useState<{
    id: string;
    checked: boolean;
  } | null>(null);
  const [members, setMembers] = useState<Collection[]>([]),
    [loaded, setLoaded] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const alive = useRef(true),
    lock = useRef(false),
    sequence = useRef(0);
  useEffect(
    () => () => {
      alive.current = false;
      sequence.current++;
    },
    [],
  );
  useEffect(() => {
    if (details.current?.open && !lock.current) void read();
  }, [catalog.items]);
  async function read() {
    const version = ++sequence.current;
    try {
      const values = await api(
        `/api/papers/${paper.id}/collections`,
        z.array(Collection),
        undefined,
        "GET",
        AbortSignal.timeout(10000),
      );
      if (alive.current && version === sequence.current) {
        setMembers(values);
        setLoaded(true);
        setError("");
        return true;
      }
    } catch (failure) {
      if (alive.current && version === sequence.current) {
        setError(String(failure));
        setLoaded(false);
      }
    }
    return false;
  }
  async function toggle(item: Collection, checked: boolean) {
    if (lock.current || !loaded) return;
    lock.current = true;
    sequence.current++;
    setBusy(true);
    setError("");
    setPending({ id: item.id, checked });
    let accepted = false;
    try {
      await api(
        `/api/papers/${paper.id}/collections/${item.id}`,
        z.unknown(),
        undefined,
        checked ? "PUT" : "DELETE",
        AbortSignal.timeout(30000),
      );
      accepted = true;
    } catch (failure) {
      if (alive.current)
        setError(`关联结果待核对，请读取最新关联。${String(failure)}`);
    } finally {
      const recovered = await read();
      lock.current = false;
      if (alive.current) {
        setBusy(false);
        setPending(null);
        if (!recovered) setLoaded(false);
      }
      if (accepted || recovered) {
        void catalog.reload();
        onChanged();
      }
    }
  }
  const all = [
    ...new Map([...catalog.items, ...members].map((c) => [c.id, c])).values(),
  ];
  return (
    <details
      ref={details}
      className="paper-organization"
      aria-label={`${paper.title} 分组与标签`}
      onToggle={(e) => {
        if (e.currentTarget.open) {
          void read();
          void catalog.load();
        }
      }}
    >
      <summary>分组与标签</summary>
      <p>逐项修改关联，不覆盖其他分组或标签。</p>
      {busy && <p role="status">正在保存关联，状态待服务器确认…</p>}
      {error && <p role="alert">{error}</p>}
      <button type="button" disabled={busy} onClick={() => void read()}>
        读取最新关联
      </button>
      {all.map((item) => (
        <label key={item.id} className="inline">
          <input
            type="checkbox"
            checked={
              pending?.id === item.id
                ? pending.checked
                : members.some((c) => c.id === item.id)
            }
            disabled={disabled || busy || !loaded}
            onChange={(e) => void toggle(item, e.target.checked)}
          />
          {labels[item.kind]}：{item.name}
        </label>
      ))}
      {!all.length && catalog.total === 0 && (
        <p>请先在“管理论文分组与标签”中创建项目分组或标签。</p>
      )}
      <CatalogControls catalog={catalog} />
    </details>
  );
}
