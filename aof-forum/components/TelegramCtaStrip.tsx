import { hubCtas } from "@/lib/aof-cta";

export function TelegramCtaStrip() {
  const ctas = hubCtas();
  return (
    <div className="cta-strip" role="complementary" aria-label="Telegram">
      {ctas.map((c) => (
        <a key={c.key} href={c.href} target="_blank" rel="noopener noreferrer">
          <span aria-hidden="true">{c.icon}</span>
          {c.label}
        </a>
      ))}
    </div>
  );
}
