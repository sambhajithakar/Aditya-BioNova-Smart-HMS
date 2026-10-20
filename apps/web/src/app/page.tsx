import { redirect } from "next/navigation";

/** middleware.ts already sends visitors without a session cookie to /login. */
export default function Home() {
  redirect("/dashboard");
}
