/**
 * Shared container for every settings page. Each page owns its heading (the
 * admin RPC pages have different titles than the account pages), so the layout
 * only normalizes width and rhythm.
 */
export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-7 pt-2">
      {children}
    </div>
  );
}
