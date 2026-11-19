import { createContext } from "react";
import type { User } from "../api/client";

export interface Credentials {
  email: string;
  password: string;
}

export interface Registration extends Credentials {
  full_name: string | null;
  consent_accepted: true;
  consent_text_version: string;
}

export interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login(credentials: Credentials): Promise<void>;
  register(data: Registration): Promise<void>;
  logout(): void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
