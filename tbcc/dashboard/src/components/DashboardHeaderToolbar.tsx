import { NavLink } from "react-router-dom";

import { useDashboardGilded } from "../context/DashboardGildedContext";

function GearIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </svg>
  );
}

function AccountIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M20 21a8 8 0 0 0-16 0" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

/** Upper-right header controls: quick gilded toggle, TBCC settings gear, account placeholder for future OAuth. */
export function DashboardHeaderToolbar() {
  const { settings: gildedSettings, updateSettings: updateGildedSettings } = useDashboardGilded();

  return (
    <div className="ml-auto flex items-center gap-2 pl-3 border-l border-slate-700/80">
      {gildedSettings.showHeaderToggle ? (
        <label className="flex items-center gap-2 text-xs text-slate-300 mr-1">
          <input
            type="checkbox"
            checked={gildedSettings.enabled}
            onChange={(e) => updateGildedSettings({ enabled: e.target.checked })}
            title="Panel accent borders (configure in Settings)"
          />
          <span title="Panel accent borders">Gilded</span>
        </label>
      ) : null}

      <NavLink
        to="/settings"
        className={({ isActive }) =>
          [
            "tbcc-header-icon-btn",
            isActive ? "tbcc-header-icon-btn--active text-cyan-400" : "text-slate-400 hover:text-slate-200",
          ].join(" ")
        }
        title="TBCC settings"
        aria-label="TBCC settings"
      >
        <GearIcon className="h-[18px] w-[18px]" />
      </NavLink>

      <button
        type="button"
        className="tbcc-header-icon-btn text-slate-600 cursor-not-allowed"
        title="Account sign-in (coming soon)"
        aria-label="Account sign-in (coming soon)"
        disabled
      >
        <AccountIcon className="h-[18px] w-[18px]" />
      </button>
    </div>
  );
}
