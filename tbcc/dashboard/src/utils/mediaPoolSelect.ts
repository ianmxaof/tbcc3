/** UI sentinel: no pool / text-only auto-pick disabled. */
export const POOL_SELECT_NONE = 0;
/** UI sentinel: each send randomly chooses one content pool. */
export const POOL_SELECT_COLLECTIVE_RANDOM = -1;

export function poolSelectUsesPool(poolSelectId: number): boolean {
  return poolSelectId > 0 || poolSelectId === POOL_SELECT_COLLECTIVE_RANDOM;
}

export function poolSelectUsesSpecificPool(poolSelectId: number): boolean {
  return poolSelectId > 0;
}

export function poolSelectFromPost(p: Record<string, unknown>): number {
  if (Boolean(p.pool_collective_random)) return POOL_SELECT_COLLECTIVE_RANDOM;
  const pid = p.pool_id != null ? Number(p.pool_id) : 0;
  return Number.isFinite(pid) && pid > 0 ? pid : POOL_SELECT_NONE;
}

export function poolSelectToApi(poolSelectId: number): {
  pool_id: number | null;
  pool_collective_random: boolean;
} {
  if (poolSelectId === POOL_SELECT_COLLECTIVE_RANDOM) {
    return { pool_id: null, pool_collective_random: true };
  }
  if (poolSelectId > 0) {
    return { pool_id: poolSelectId, pool_collective_random: false };
  }
  return { pool_id: null, pool_collective_random: false };
}

export function poolSelectLabel(poolSelectId: number, poolName?: string): string {
  if (poolSelectId === POOL_SELECT_COLLECTIVE_RANDOM) return "All pools (random)";
  if (poolSelectId > 0) return poolName || `Pool ${poolSelectId}`;
  return "—";
}

export function poolAlbumDefaultsFromMap(
  poolSelectId: number,
  poolMap: Record<string, Record<string, unknown>>
): { albumSize: number; randomize: boolean } {
  if (poolSelectId === POOL_SELECT_COLLECTIVE_RANDOM) {
    return { albumSize: 5, randomize: true };
  }
  if (poolSelectId <= 0) {
    return { albumSize: 5, randomize: false };
  }
  const pool = poolMap[String(poolSelectId)];
  return {
    albumSize: Math.min(10, Math.max(1, Number(pool?.album_size ?? 5))),
    randomize: Boolean(pool?.randomize_queue),
  };
}
