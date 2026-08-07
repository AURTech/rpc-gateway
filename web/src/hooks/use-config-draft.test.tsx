import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useConfigDraft } from "./use-config-draft";

describe("useConfigDraft", () => {
  it("accepts remote refreshes while clean", () => {
    const { result, rerender } = renderHook(
      ({ remote }) => useConfigDraft(remote),
      { initialProps: { remote: { value: 1 } } },
    );

    rerender({ remote: { value: 2 } });

    expect(result.current.draft).toEqual({ value: 2 });
    expect(result.current.dirty).toBe(false);
  });

  it("keeps a dirty draft and reports a remote change", () => {
    const { result, rerender } = renderHook(
      ({ remote }) => useConfigDraft(remote),
      { initialProps: { remote: { value: 1 } } },
    );
    act(() => result.current.setDraft({ value: 3 }));

    rerender({ remote: { value: 2 } });

    expect(result.current.draft).toEqual({ value: 3 });
    expect(result.current.remoteChanged).toBe(true);
  });

  it("can accept the server version or rebase the local draft", () => {
    const { result, rerender } = renderHook(
      ({ remote }) => useConfigDraft(remote),
      { initialProps: { remote: { value: 1 } } },
    );
    act(() => result.current.setDraft({ value: 3 }));
    rerender({ remote: { value: 2 } });

    act(() => result.current.reapplyLocal());
    expect(result.current.draft).toEqual({ value: 3 });
    expect(result.current.baseline).toEqual({ value: 2 });

    act(() => result.current.acceptRemote());
    expect(result.current.draft).toEqual({ value: 2 });
    expect(result.current.dirty).toBe(false);
  });
});
