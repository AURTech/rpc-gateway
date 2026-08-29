/** Shared, bounded layout for every App settings sub-page. */
export default function AppSettingsLayout({
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
