// Who is signed in, for every screen (PLAN-DEV-B 3.3). AuthProvider fills it.
// Owner: B

import { createContext, useContext } from "react";
import type { components } from "../../api/schema";

export type User = components["schemas"]["User"];

export type AuthState =
  | { status: "loading" }
  | { status: "signed_out" }
  | { status: "signed_in"; user: User }
  // The server didn't answer /auth/me: not the same as signed out.
  | { status: "error"; message: string };

export type Auth = {
  state: AuthState;
  /** Resolves once signed in; throws the ApiError otherwise. */
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Ask /auth/me again, after an error. */
  retry: () => void;
};

export const AuthContext = createContext<Auth | null>(null);

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (auth === null) throw new Error("useAuth needs an AuthProvider above it");
  return auth;
}
