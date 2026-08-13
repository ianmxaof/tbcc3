/** Local dev: password sign-in when Supabase built-in email rate limits block magic links. */
export function devPasswordAuthEnabled(): boolean {
  return process.env.NEXT_PUBLIC_DEV_PASSWORD_AUTH === "1";
}

export function isEmailRateLimitError(message: string): boolean {
  return /rate limit|too many requests|email.*limit/i.test(message);
}

export function rateLimitHelpText(): string {
  return (
    "Supabase blocks more magic-link emails per hour on the built-in SMTP (~4/hr on free tier). " +
    "Wait 60 minutes, use Password sign-in below (create user in Supabase Dashboard → Authentication → Users), " +
    "or add custom SMTP under Authentication → SMTP Settings."
  );
}
