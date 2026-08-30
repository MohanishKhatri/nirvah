"use client";

import { signIn, signOut, useSession } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";

const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";
const ALLOWED_DOMAIN = process.env.NEXT_PUBLIC_ALLOWED_DOMAIN ?? "nitk.edu.in";
const DEMO_KEY = "nirvah_demo_student";

export interface Identity {
  ready: boolean;
  authed: boolean;
  email: string | null;
  /** Google ID token for the backend. Empty string in demo/mock mode. */
  idToken: string;
  isDemo: boolean;
}

/**
 * Wraps NextAuth so pages have one identity source.
 *
 * A demo student can always be used instead of Google — useful before OAuth credentials
 * exist. This is independent of NEXT_PUBLIC_USE_MOCKS: the demo email plus an empty idToken
 * is enough for the real backend too, as long as it has DEV_AUTH_BYPASS=true (it accepts any
 * bearer token, including a missing one, before it ever looks at the token's contents).
 */
export function useIdentity() {
  const { data: session, status } = useSession();
  const [demoEmail, setDemoEmail] = useState<string | null>(null);
  const [demoChecked, setDemoChecked] = useState(false);

  useEffect(() => {
    setDemoEmail(sessionStorage.getItem(DEMO_KEY));
    setDemoChecked(true);
  }, []);

  const enterDemo = useCallback(() => {
    const email = `demo.student@${ALLOWED_DOMAIN}`;
    sessionStorage.setItem(DEMO_KEY, email);
    setDemoEmail(email);
  }, []);

  const leave = useCallback(() => {
    sessionStorage.removeItem(DEMO_KEY);
    setDemoEmail(null);
    if (session) void signOut({ callbackUrl: "/" });
  }, [session]);

  const isDemo = Boolean(demoEmail && !session);

  const identity: Identity = {
    ready: demoChecked && status !== "loading",
    authed: Boolean(session) || isDemo,
    email: session?.user?.email ?? demoEmail,
    idToken: session?.idToken ?? "",
    isDemo,
  };

  return {
    ...identity,
    mocksEnabled: USE_MOCKS,
    signInGoogle: () => signIn("google"),
    signOutAll: leave,
    enterDemo,
  };
}
