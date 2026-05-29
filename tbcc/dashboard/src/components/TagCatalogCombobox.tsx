import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import {
  autocompleteRemainder,
  catalogRowsForPicker,
  searchCatalogTags,
  tagPickerLabel,
  type TagCatalogRow,
} from "../lib/tagCatalogSearch";

type BaseProps = {
  tags: TagCatalogRow[];
  /** Hide hex-ID-like catalog rows in the picker. */
  hideJunk?: boolean;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  maxListHeightClass?: string;
};

type AddProps = BaseProps & {
  mode: "add";
  onPick: (label: string, row: TagCatalogRow) => void;
};

type FilterProps = BaseProps & {
  mode: "filter";
  value: string;
  onChange: (slug: string) => void;
  anyLabel?: string;
};

export type TagCatalogComboboxProps = AddProps | FilterProps;

export function TagCatalogCombobox(props: TagCatalogComboboxProps) {
  const {
    tags,
    hideJunk = true,
    placeholder = "Search catalog…",
    className = "",
    disabled = false,
    maxListHeightClass = "max-h-48",
  } = props;

  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);

  const pickerRows = useMemo(() => {
    const base = hideJunk ? catalogRowsForPicker(tags).kept : tags;
    return [...base].sort((a, b) => tagPickerLabel(a).localeCompare(tagPickerLabel(b), undefined, { sensitivity: "base" }));
  }, [tags, hideJunk]);

  const { items, prefixLabel } = useMemo(
    () => searchCatalogTags(pickerRows, open ? query : "", 48),
    [pickerRows, query, open]
  );

  const ghostSuffix = useMemo(() => {
    if (!open || !query.trim() || !prefixLabel) return "";
    return autocompleteRemainder(query, prefixLabel);
  }, [open, query, prefixLabel]);

  useEffect(() => {
    setHighlight(0);
  }, [query, items.length]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const commitPick = useCallback(
    (row: TagCatalogRow) => {
      const label = tagPickerLabel(row);
      if (!label) return;
      if (props.mode === "add") {
        props.onPick(label, row);
        setQuery("");
        setOpen(false);
        inputRef.current?.focus();
      } else {
        props.onChange(row.slug);
        setQuery("");
        setOpen(false);
      }
    },
    [props]
  );

  const acceptGhost = useCallback(() => {
    if (ghostSuffix && prefixLabel) {
      setQuery(prefixLabel);
      return true;
    }
    return false;
  }, [ghostSuffix, prefixLabel]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Tab" && open && ghostSuffix) {
      e.preventDefault();
      acceptGhost();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) setOpen(true);
      setHighlight((i) => Math.min(i + 1, Math.max(0, items.length - 1)));
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) setOpen(true);
      setHighlight((i) => Math.max(i - 1, 0));
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (open && items[highlight]) {
        commitPick(items[highlight]);
      } else if (props.mode === "filter" && !query.trim()) {
        props.onChange("");
        setOpen(false);
      }
      return;
    }
    if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
      if (props.mode === "filter" && props.value) {
        setQuery(props.value);
      }
    }
  };

  const filterValue = props.mode === "filter" ? props.value : "";
  const displayValue =
    open || query.length > 0 ? query : props.mode === "filter" && filterValue ? filterValue : "";

  const showList = open && !disabled && (items.length > 0 || (props.mode === "filter" && !query.trim()));

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
          placeholder={placeholder}
          value={displayValue}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => {
            setOpen(true);
            if (props.mode === "filter" && filterValue && !query) setQuery(filterValue);
          }}
          onKeyDown={onKeyDown}
          className="w-full bg-slate-800 border border-slate-600 rounded px-2 py-1 text-slate-200 text-sm pr-2"
          title="Type to search; Tab completes suggestion; ↑↓ highlight; Enter to select"
        />
        {ghostSuffix ? (
          <span
            className="pointer-events-none absolute inset-y-0 left-0 flex items-center px-2 text-sm whitespace-pre"
            aria-hidden
          >
            <span className="invisible">{displayValue}</span>
            <span className="text-slate-500">{ghostSuffix}</span>
          </span>
        ) : null}
      </div>
      {showList ? (
        <ul
          id={listId}
          role="listbox"
          className={`absolute z-50 mt-0.5 w-full overflow-y-auto rounded border border-slate-600 bg-slate-900 shadow-lg text-sm ${maxListHeightClass}`}
        >
          {props.mode === "filter" && !query.trim() ? (
            <li role="option" aria-selected={!filterValue}>
              <button
                type="button"
                className={`w-full text-left px-2 py-1.5 hover:bg-slate-700 ${!filterValue ? "bg-cyan-900/40 text-cyan-200" : "text-slate-300"}`}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  props.onChange("");
                  setQuery("");
                  setOpen(false);
                }}
              >
                {props.anyLabel ?? "(any)"}
              </button>
            </li>
          ) : null}
          {items.map((row, i) => {
            const label = tagPickerLabel(row);
            const sub = row.slug && label.toLowerCase() !== row.slug.toLowerCase() ? row.slug : null;
            const active = i === highlight;
            return (
              <li key={row.id} role="option" aria-selected={active}>
                <button
                  type="button"
                  className={`w-full text-left px-2 py-1.5 hover:bg-slate-700 ${active ? "bg-cyan-900/40 text-cyan-100" : "text-slate-200"}`}
                  onMouseEnter={() => setHighlight(i)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => commitPick(row)}
                >
                  <span className="font-medium">{label}</span>
                  {sub ? <span className="text-slate-500 text-xs ml-1.5 font-mono">{sub}</span> : null}
                </button>
              </li>
            );
          })}
          {items.length === 0 && query.trim() ? (
            <li className="px-2 py-2 text-slate-500 text-xs">No matching tags</li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
