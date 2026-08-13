/**
 * Create or reset a local dev user (email + password, auto-confirmed).
 * Use when magic-link rate limits block sign-in.
 *
 *   npm run dev:bootstrap-user -- you@example.com YourPassword
 */
import { config } from "dotenv";
import path from "node:path";
import { createAdminClient } from "../lib/supabase/admin";

const root = process.cwd();
config({ path: path.join(root, ".env.local") });
config({ path: path.join(root, ".env") });

async function main() {
  const email = process.argv[2]?.trim();
  const password = process.argv[3];
  if (!email || !password) {
    console.error("Usage: npm run dev:bootstrap-user -- <email> <password>");
    process.exit(1);
  }
  if (password.length < 8) {
    console.error("Password must be at least 8 characters.");
    process.exit(1);
  }

  const db = createAdminClient();
  const { data: listed, error: listErr } = await db.auth.admin.listUsers({ page: 1, perPage: 1000 });
  if (listErr) {
    console.error("listUsers failed:", listErr.message);
    process.exit(1);
  }

  const existing = listed.users.find((u) => u.email?.toLowerCase() === email.toLowerCase());

  if (existing) {
    const { data, error } = await db.auth.admin.updateUserById(existing.id, {
      password,
      email_confirm: true,
    });
    if (error) {
      console.error("updateUser failed:", error.message);
      process.exit(1);
    }
    console.log(`Updated user ${data.user.email} (id=${data.user.id}) — password set, email confirmed.`);
  } else {
    const { data, error } = await db.auth.admin.createUser({
      email,
      password,
      email_confirm: true,
    });
    if (error) {
      console.error("createUser failed:", error.message);
      process.exit(1);
    }
    console.log(`Created user ${data.user.email} (id=${data.user.id}) — auto-confirmed.`);
  }

  console.log("\nSign in at http://localhost:3001/auth/sign-in → Password (dev)");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
