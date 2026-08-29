import { redirect } from "next/navigation";

export default async function ProvidersPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect(`/${locale}/dashboard/endpoints?workspace=providers`);
}
