import { useEffect } from "react";
import {
  ClerkProvider,
  SignedIn,
  SignedOut,
  SignIn,
  useAuth,
} from "@clerk/clerk-react";
import { setAuthTokenGetter } from "../api";

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

// True only when Clerk is configured for this build. Used elsewhere to decide
// whether to render account/billing controls.
export const AUTH_ENABLED = Boolean(PUBLISHABLE_KEY);

// Wires Clerk's getToken into the API layer so every request is authenticated.
function TokenBridge() {
  const { getToken, isSignedIn } = useAuth();

  useEffect(() => {
    setAuthTokenGetter(async () => {
      try {
        return await getToken();
      } catch {
        return null;
      }
    });
    return () => setAuthTokenGetter(null);
  }, [getToken, isSignedIn]);

  return null;
}

export default function AuthGate({ children }) {
  // No publishable key -> auth disabled: render the app exactly as before.
  if (!AUTH_ENABLED) {
    return children;
  }

  return (
    <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">
      <TokenBridge />
      <SignedIn>{children}</SignedIn>
      <SignedOut>
        <div
          className="flex h-screen items-center justify-center p-6"
          style={{ background: "var(--bg-base)" }}
        >
          <SignIn routing="hash" />
        </div>
      </SignedOut>
    </ClerkProvider>
  );
}
