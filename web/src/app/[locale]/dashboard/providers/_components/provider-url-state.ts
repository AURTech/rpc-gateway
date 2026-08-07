/**
 * Mirrors the open drawer into the URL without starting an App Router
 * navigation. The provider page reads this parameter on a real navigation or
 * reload, while in-place drawer changes stay entirely client-side.
 */
export function replaceProviderSearchParam(providerId: string | null) {
  const url = new URL(window.location.href);

  if (providerId) {
    url.searchParams.set("provider", providerId);
  } else {
    url.searchParams.delete("provider");
  }

  window.history.replaceState(
    window.history.state,
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
}
