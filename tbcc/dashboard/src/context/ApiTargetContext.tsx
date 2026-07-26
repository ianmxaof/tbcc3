import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  API_TARGET_META,
  canSwitchApiTarget,
  getApiBase,
  getApiTarget,
  setApiTarget,
  subscribeApiTarget,
  type ApiTarget,
} from "../apiConfig";

type ApiTargetContextValue = {
  target: ApiTarget;
  apiBase: string;
  canSwitch: boolean;
  meta: (typeof API_TARGET_META)[ApiTarget];
  setTarget: (target: ApiTarget) => void;
};

const ApiTargetContext = createContext<ApiTargetContextValue | null>(null);

export function ApiTargetProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [target, setTargetState] = useState<ApiTarget>(() => getApiTarget());

  useEffect(() => subscribeApiTarget(() => setTargetState(getApiTarget())), []);

  const setTarget = useCallback(
    (next: ApiTarget) => {
      if (next === getApiTarget()) return;
      setApiTarget(next);
      queryClient.clear();
    },
    [queryClient]
  );

  const value = useMemo(
    (): ApiTargetContextValue => ({
      target,
      apiBase: getApiBase(),
      canSwitch: canSwitchApiTarget(),
      meta: API_TARGET_META[target],
      setTarget,
    }),
    [target, setTarget]
  );

  return <ApiTargetContext.Provider value={value}>{children}</ApiTargetContext.Provider>;
}

export function useApiTarget(): ApiTargetContextValue {
  const ctx = useContext(ApiTargetContext);
  if (!ctx) throw new Error("useApiTarget must be used within ApiTargetProvider");
  return ctx;
}
