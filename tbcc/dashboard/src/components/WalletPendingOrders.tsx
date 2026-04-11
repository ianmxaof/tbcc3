import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

type Row = {
  id: number;
  telegram_user_id: number;
  plan_id: number;
  reference_code: string;
  status: string;
  created_at?: string | null;
  plan_name?: string | null;
  price_stars?: number | null;
};

/**
 * Admin: wallet / manual (crypto, Cash App, etc.) orders stay pending until someone calls mark-paid.
 * Dev: Vite proxy injects TBCC_INTERNAL_API_KEY from tbcc/.env — see vite.config.ts.
 */
export function WalletPendingOrders() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["external-payment-orders", "pending"],
    queryFn: () => api.externalPaymentOrders.listPending(),
  });

  const markPaid = useMutation({
    mutationFn: (orderId: number) => api.externalPaymentOrders.markPaid(orderId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["external-payment-orders"] }),
  });

  return (
    <div className="mt-10 border-t border-slate-700 pt-8">
      <h2 className="text-lg font-semibold text-slate-100 mb-2">Pending wallet / crypto orders</h2>
      <p className="text-slate-400 text-sm mb-4 max-w-3xl leading-relaxed">
        <strong className="text-slate-300">Automatic path:</strong> configure NOWPayments + a public{" "}
        <code className="text-cyan-300/90">https://</code> API base so IPN hits{" "}
        <code className="text-cyan-300/90">/webhooks/nowpayments</code> — orders clear without this list.{" "}
        <strong className="text-slate-300">Manual path:</strong> if someone paid outside automation, use{" "}
        <strong>Mark paid</strong> with the <code className="text-cyan-300/90">EPO-…</code> reference.
      </p>
      <p className="text-amber-200/90 text-xs mb-4 bg-amber-950/30 border border-amber-800/40 rounded px-3 py-2">
        If this list fails with 403, set <code className="text-amber-100">TBCC_INTERNAL_API_KEY</code> in{" "}
        <code className="text-amber-100">tbcc/.env</code> (same value as the API), restart{" "}
        <code className="text-amber-100">npm run dev</code> so Vite reloads env, and ensure the payment bot uses the same key.
      </p>

      {q.isError && (
        <p className="text-red-400 text-sm mb-4">
          {(q.error as Error)?.message || "Could not load pending orders."}
        </p>
      )}

      {q.isPending && <p className="text-slate-500 text-sm">Loading…</p>}

      {q.data && q.data.length === 0 && !q.isPending && (
        <p className="text-slate-500 text-sm">No pending wallet orders.</p>
      )}

      {q.data && q.data.length > 0 && (
        <div className="overflow-x-auto border border-slate-600 rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-slate-800 text-slate-400 text-left">
              <tr>
                <th className="p-2">Ref</th>
                <th className="p-2">User TG id</th>
                <th className="p-2">Product</th>
                <th className="p-2">Stars (ref)</th>
                <th className="p-2">Created</th>
                <th className="p-2 w-28">Action</th>
              </tr>
            </thead>
            <tbody>
              {(q.data as Row[]).map((r) => (
                <tr key={r.id} className="border-t border-slate-700">
                  <td className="p-2 font-mono text-cyan-300/90">{r.reference_code}</td>
                  <td className="p-2 text-slate-300">{r.telegram_user_id}</td>
                  <td className="p-2 text-slate-200">
                    {r.plan_name ?? `plan #${r.plan_id}`}
                  </td>
                  <td className="p-2 text-slate-400">{r.price_stars ?? "—"}</td>
                  <td className="p-2 text-slate-500 text-xs whitespace-nowrap">
                    {r.created_at ? String(r.created_at).slice(0, 19) : "—"}
                  </td>
                  <td className="p-2">
                    <button
                      type="button"
                      disabled={markPaid.isPending}
                      onClick={() => {
                        if (
                          confirm(
                            `Mark ${r.reference_code} paid and grant access?\nUser ${r.telegram_user_id} / ${r.plan_name ?? r.plan_id}`
                          )
                        )
                          markPaid.mutate(r.id);
                      }}
                      className="px-2 py-1 rounded bg-green-800 text-green-100 text-xs hover:bg-green-700 disabled:opacity-50"
                    >
                      Mark paid
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
