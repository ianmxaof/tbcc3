import {
  POOL_SELECT_COLLECTIVE_RANDOM,
  POOL_SELECT_NONE,
} from "../utils/mediaPoolSelect";

type PoolRow = { id: number; name?: string };

type Props = {
  value: number;
  onChange: (poolSelectId: number) => void;
  pools: PoolRow[];
  className?: string;
  /** Short labels for compact composer tiles. */
  variant?: "compact" | "full";
};

export function MediaPoolSelect({
  value,
  onChange,
  pools,
  className = "",
  variant = "full",
}: Props) {
  const noPoolLabel =
    variant === "compact"
      ? "No pool"
      : "No pool (text-only unless media is explicitly picked below)";
  const collectiveLabel =
    variant === "compact"
      ? "All pools (random)"
      : "All pools (random) — each send picks one pool, then auto-picks media";
  const poolSuffix = variant === "compact" ? "" : " (media + optional auto-pick)";

  return (
    <select
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className={className}
    >
      <option value={POOL_SELECT_NONE}>{noPoolLabel}</option>
      <option value={POOL_SELECT_COLLECTIVE_RANDOM}>{collectiveLabel}</option>
      {pools.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name || `Pool ${p.id}`}
          {poolSuffix}
        </option>
      ))}
    </select>
  );
}
