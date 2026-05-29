import { TopBar } from "@/components/TopBar";
import { LeftNav } from "@/components/LeftNav";

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <TopBar />
      <LeftNav />
      <main className="main">{children}</main>
    </div>
  );
}
