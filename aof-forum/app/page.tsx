export default function HomePage() {
  return (
    <>
      <h1>AOF Hub</h1>
      <p className="muted">
        Forum-first scaffold: Next.js (App Router) on Vercel, Supabase for Postgres + Auth.
        TBCC / Telegram funnels link here with UTM params; optional server routes can call your
        TBCC API with a server-only key.
      </p>
      <div className="card">
        <p>
          <strong>Next:</strong> enable Supabase env vars in Vercel, run SQL for categories/threads,
          add auth UI, then wire scheduled Telegram posts to canonical URLs on this domain.
        </p>
      </div>
    </>
  );
}
