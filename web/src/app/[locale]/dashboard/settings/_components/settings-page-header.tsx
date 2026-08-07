/** Page heading shared by the settings sub-pages (account + admin RPC). */
export function SettingsPageHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  return (
    <header className="flex flex-col gap-1.5">
      <h1 className="text-3xl font-bold tracking-tight text-ink-900">
        {title}
      </h1>
      <p className="max-w-prose-narrow text-md text-ink-500">{subtitle}</p>
    </header>
  );
}
