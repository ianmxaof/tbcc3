export function QueryErrorBanner({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="rounded-lg bg-red-900/30 border border-red-700 p-3 text-red-200 text-sm mb-4">
      <p className="font-medium">{title}</p>
      <p className="text-red-300/90 text-xs mt-1 whitespace-pre-wrap">{message}</p>
      <button type="button" onClick={onRetry} className="mt-2 px-3 py-1 rounded bg-red-800 hover:bg-red-700 text-xs">
        Retry
      </button>
    </div>
  );
}
