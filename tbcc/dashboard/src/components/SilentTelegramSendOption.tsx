/** Shared checkbox for Telegram channel/group posts (disable_notification / Telethon silent). */
export function SilentTelegramSendOption({
  checked,
  onChange,
  className = "",
  disabled = false,
  compact = false,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  className?: string;
  disabled?: boolean;
  /** Shorter label without helper line (dense toolbars). */
  compact?: boolean;
}) {
  return (
    <label
      className={`flex items-start gap-2 text-sm text-slate-300 cursor-pointer ${disabled ? "opacity-50 cursor-not-allowed" : ""} ${className}`}
    >
      <input
        type="checkbox"
        className="mt-0.5 shrink-0"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      {compact ? (
        <span>Silent post (no subscriber notification)</span>
      ) : (
        <span>
          <strong className="text-slate-200">Silent post</strong>
          <span className="block text-xs text-slate-500 mt-0.5">
            Followers won’t get a push notification for this message (Telegram sends without alerting subscribers).
          </span>
        </span>
      )}
    </label>
  );
}

export const TBCC_SEND_SILENT_STORAGE_KEY = "tbcc-dashboard-send-silent";

export function readSendSilentPreference(): boolean {
  try {
    return localStorage.getItem(TBCC_SEND_SILENT_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeSendSilentPreference(value: boolean): void {
  try {
    localStorage.setItem(TBCC_SEND_SILENT_STORAGE_KEY, value ? "1" : "0");
  } catch {
    /* ignore */
  }
}
