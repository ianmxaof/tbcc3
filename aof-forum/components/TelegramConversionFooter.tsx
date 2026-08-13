import type { CtaContext } from "@/lib/aof-cta";
import { contextualCtas } from "@/lib/aof-cta";

export function TelegramConversionFooter({
  context,
  title = "Continue on Telegram",
}: {
  context: CtaContext;
  title?: string;
}) {
  const ctas = contextualCtas(context);
  return (
    <section className="conversion-footer" aria-label={title}>
      <h3 style={{ margin: "0 0 0.5rem", fontSize: "1rem" }}>{title}</h3>
      <p className="muted" style={{ fontSize: "0.85rem", margin: "0 0 0.65rem" }}>
        Owned bots — keys, VIP, companion. One tap.
      </p>
      <div className="cta-strip" style={{ marginBottom: 0 }}>
        {ctas.map((c) => (
          <a key={c.key} href={c.href} target="_blank" rel="noopener noreferrer">
            <span aria-hidden="true">{c.icon}</span>
            {c.label}
          </a>
        ))}
      </div>
    </section>
  );
}
