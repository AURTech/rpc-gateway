"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { isApiError } from "@/api/client";

export const CONFIG_CONFLICT_MESSAGE =
  "Configuration changed. Refresh before saving.";

export function isConfigConflict(error: unknown): boolean {
  return (
    isApiError(error) &&
    error.status === 400 &&
    error.message === CONFIG_CONFLICT_MESSAGE
  );
}

function equal<T>(left: T, right: T): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function useConfigDraft<T>(remote: T) {
  const [baseline, setBaseline] = useState(remote);
  const [draft, setDraft] = useState(remote);
  const [latestRemote, setLatestRemote] = useState(remote);
  const [remoteChanged, setRemoteChanged] = useState(false);
  const draftRef = useRef(draft);
  const baselineRef = useRef(baseline);
  draftRef.current = draft;
  baselineRef.current = baseline;

  useEffect(() => {
    setLatestRemote(remote);
    if (equal(draftRef.current, baselineRef.current)) {
      setBaseline(remote);
      setDraft(remote);
      setRemoteChanged(false);
    } else if (!equal(remote, baselineRef.current)) {
      setRemoteChanged(true);
    }
  }, [remote]);

  const reset = useCallback(() => {
    setBaseline(latestRemote);
    setDraft(latestRemote);
    setRemoteChanged(false);
  }, [latestRemote]);

  const reapplyLocal = useCallback(() => {
    setBaseline(latestRemote);
    setRemoteChanged(false);
  }, [latestRemote]);

  const commit = useCallback((saved: T) => {
    setBaseline(saved);
    setDraft(saved);
    setLatestRemote(saved);
    setRemoteChanged(false);
  }, []);

  return {
    baseline,
    draft,
    setDraft,
    dirty: !equal(draft, baseline),
    remoteChanged,
    reset,
    acceptRemote: reset,
    reapplyLocal,
    commit,
  };
}

export function useUnsavedChangesGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);
}
