import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

type Eff = {
  landing_bulletin_chat_id?: string;
  landing_bulletin_message_thread_id?: number | null;
  landing_bulletin_hour_utc?: number;
  landing_bulletin_bot_username?: string;
  landing_bulletin_intro?: string | null;
  referral_group_invite_link?: string;
  referral_group_name?: string;
  referral_reward_days?: number;
  referral_mode?: string;
  milestone_progress_chat_id?: string;
};

const empty: Eff = {
  landing_bulletin_chat_id: "",
  landing_bulletin_hour_utc: 14,
  landing_bulletin_bot_username: "",
  landing_bulletin_intro: "",
  referral_group_invite_link: "",
  referral_group_name: "our community",
  referral_reward_days: 7,
  referral_mode: "premium",
  milestone_progress_chat_id: "",
};

export function Growth() {
  const qc = useQueryClient();
  const {
    data,
    isPending,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["growth-settings"],
    queryFn: () => api.growthSettings.get(),
  });

  const [form, setForm] = useState<Eff>(empty);

  useEffect(() => {
    const eff = data?.effective as Eff | undefined;
    if (!eff) return;
    setForm({
      ...empty,
      ...eff,
      landing_bulletin_intro: eff.landing_bulletin_intro ?? "",
      landing_bulletin_message_thread_id: eff.landing_bulletin_message_thread_id ?? undefined,
    });
  }, [data]);

  const postNow = useMutation({
    mutationFn: () => api.growthSettings.sendBulletinNow(),
  });

  const save = useMutation({
    mutationFn: () => {
      const threadRaw = form.landing_bulletin_message_thread_id;
      let thread: number | null = null;
      if (typeof threadRaw === "number" && threadRaw > 0) {
        thread = threadRaw;
      }
      return api.growthSettings.patch({
        landing_bulletin_chat_id: form.landing_bulletin_chat_id?.trim() || null,
        landing_bulletin_message_thread_id: thread,
        landing_bulletin_hour_utc:
          form.landing_bulletin_hour_utc != null ? Math.min(23, Math.max(0, Number(form.landing_bulletin_hour_utc))) : null,
        landing_bulletin_bot_username: form.landing_bulletin_bot_username?.trim() || null,
        landing_bulletin_intro: (form.landing_bulletin_intro || "").trim() || null,
        referral_group_invite_link: form.referral_group_invite_link?.trim() || null,
        referral_group_name: form.referral_group_name?.trim() || null,
        referral_reward_days: form.referral_reward_days != null ? Number(form.referral_reward_days) : null,
        referral_mode: form.referral_mode || null,
        milestone_progress_chat_id: form.milestone_progress_chat_id?.trim() || null,
      });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["growth-settings"] }),
  });

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-semibold mb-2">Growth &amp; referrals</h1>
      <p className="text-slate-400 text-sm mb-3">
        Values here override <code className="text-slate-300">tbcc/.env</code> for the payment bot, landing bulletin, and
        milestone FOMO posts. Clear a field and save to fall back to env again.
      </p>
      <div className="bg-slate-900/90 border border-slate-600 rounded-lg p-4 mb-6 text-sm text-slate-300 space-y-2">
        <p className="font-medium text-slate-100">Default test routing (see <code className="text-cyan-300">tbcc/docs/GROWTH.md</code>)</p>
        <p>
          <strong>Landing chat id</strong> and <strong>Milestone progress chat id</strong> are set to your{" "}
          <strong>Telegram user id</strong> (same as <code className="text-slate-200">ADMIN_TELEGRAM_ID</code> in{" "}
          <code className="text-slate-200">tbcc/.env</code>) so the bot <strong>DMs you</strong> bulletin + FOMO for safe
          testing. You must have <code className="text-slate-200">/start</code>ed the payment bot.
        </p>
        <p>
          For production, replace both with your real <code className="text-slate-200">@channel</code> or{" "}
          <code className="text-slate-200">-100…</code> targets — not the <code className="text-slate-200">t.me/+…</code> invite
          hash.
        </p>
      </div>

      {isError && (
        <QueryErrorBanner
          title="Could not load growth settings"
          message={String((error as Error)?.message ?? error)}
          onRetry={() => void refetch()}
        />
      )}

      {isPending && <p className="text-slate-400">Loading…</p>}

      {!isPending && data && (
        <form
          className="space-y-8"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <section className="bg-slate-800 rounded-lg p-4 border border-slate-700">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
              <h2 className="text-lg font-medium">Daily landing bulletin (Telegram)</h2>
              <button
                type="button"
                onClick={() => postNow.mutate()}
                disabled={postNow.isPending || !(form.landing_bulletin_chat_id ?? "").toString().trim()}
                title={
                  (form.landing_bulletin_chat_id ?? "").toString().trim()
                    ? "Queue send now (ignores UTC hour). Requires Celery worker + Redis."
                    : "Set Landing chat id first (save or .env)"
                }
                className="shrink-0 px-4 py-2 rounded border border-amber-500/80 bg-amber-500/15 text-amber-200 hover:bg-amber-500/25 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {postNow.isPending ? "Posting…" : "Post now"}
              </button>
            </div>
            {postNow.isError && (
              <p className="text-red-400 text-sm mb-2">{(postNow.error as Error)?.message ?? "Post failed"}</p>
            )}
            {postNow.isSuccess && postNow.data && (
              <p className="text-green-400 text-sm mb-2">
                {postNow.data.message} Task: <code className="text-slate-300">{postNow.data.task_id}</code>
              </p>
            )}
            <p className="text-slate-400 text-sm mb-4">
              Scheduled hourly; only your <strong>UTC hour</strong> sends automatically. <strong>Post now</strong> sends
              immediately (same copy as below). Use numeric chat id (e.g.{" "}
              <code className="text-slate-300">-100…</code>) or public <code className="text-slate-300">@channel</code>.
            </p>
            <div className="grid gap-3">
              <label className="block">
                <span className="text-slate-400 text-sm">Landing chat id</span>
                <input
                  className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                  value={form.landing_bulletin_chat_id ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, landing_bulletin_chat_id: e.target.value }))}
                  placeholder="-100xxxxxxxxxx or @YourChannel"
                />
              </label>
              <label className="block">
                <span className="text-slate-400 text-sm">Forum topic id (optional)</span>
                <input
                  type="number"
                  className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                  value={form.landing_bulletin_message_thread_id ?? ""}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      landing_bulletin_message_thread_id: e.target.value === "" ? undefined : Number(e.target.value),
                    }))
                  }
                  placeholder="Leave empty for main chat"
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-slate-400 text-sm">Send hour (UTC)</span>
                  <input
                    type="number"
                    min={0}
                    max={23}
                    className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    value={form.landing_bulletin_hour_utc ?? 14}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, landing_bulletin_hour_utc: Number(e.target.value) }))
                    }
                  />
                </label>
                <label className="block">
                  <span className="text-slate-400 text-sm">Bot username (for t.me link)</span>
                  <input
                    className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    value={form.landing_bulletin_bot_username ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, landing_bulletin_bot_username: e.target.value }))}
                    placeholder="Without @"
                  />
                </label>
              </div>
              <label className="block">
                <span className="text-slate-400 text-sm">Custom intro (optional — multiline)</span>
                <textarea
                  rows={5}
                  className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100 font-mono text-sm"
                  value={form.landing_bulletin_intro ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, landing_bulletin_intro: e.target.value }))}
                  placeholder="Empty = default AOF bullets from the server"
                />
              </label>
            </div>
          </section>

          <section className="bg-slate-800 rounded-lg p-4 border border-slate-700">
            <h2 className="text-lg font-medium mb-3">Referrals (bot copy)</h2>
            <div className="grid gap-3">
              <label className="block">
                <span className="text-slate-400 text-sm">Group invite link</span>
                <input
                  className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                  value={form.referral_group_invite_link ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, referral_group_invite_link: e.target.value }))}
                />
              </label>
              <label className="block">
                <span className="text-slate-400 text-sm">Group display name</span>
                <input
                  className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                  value={form.referral_group_name ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, referral_group_name: e.target.value }))}
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-slate-400 text-sm">Reward days (referrer)</span>
                  <input
                    type="number"
                    min={1}
                    className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    value={form.referral_reward_days ?? 7}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, referral_reward_days: Number(e.target.value) }))
                    }
                  />
                </label>
                <label className="block">
                  <span className="text-slate-400 text-sm">Mode</span>
                  <select
                    className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    value={form.referral_mode ?? "premium"}
                    onChange={(e) => setForm((f) => ({ ...f, referral_mode: e.target.value }))}
                  >
                    <option value="community">Community (invite-first)</option>
                    <option value="premium">Premium (paid rewards)</option>
                  </select>
                </label>
              </div>
            </div>
          </section>

          <section className="bg-slate-800 rounded-lg p-4 border border-slate-700">
            <h2 className="text-lg font-medium mb-3">Milestone “progress” line</h2>
            <p className="text-slate-400 text-sm mb-3">
              Optional chat id where the bot posts the subscriber-count progress line after new subscriptions.
            </p>
            <label className="block">
              <span className="text-slate-400 text-sm">Milestone progress chat id</span>
              <input
                className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                value={form.milestone_progress_chat_id ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, milestone_progress_chat_id: e.target.value }))}
                placeholder="Same as landing or a group — optional"
              />
            </label>
          </section>

          {save.isError && (
            <p className="text-red-400 text-sm">{(save.error as Error)?.message ?? "Save failed"}</p>
          )}
          {save.isSuccess && <p className="text-green-400 text-sm">Saved.</p>}

          <button
            type="submit"
            disabled={save.isPending}
            className="px-4 py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-medium disabled:opacity-50"
          >
            {save.isPending ? "Saving…" : "Save growth settings"}
          </button>
        </form>
      )}
    </div>
  );
}
