"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import type { AbstractIntlMessages } from "next-intl";
import { NextIntlClientProvider } from "next-intl";
import { ThemeProvider } from "next-themes";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { getQueryClient } from "@/lib/query-client";

interface ProvidersProps {
  children: React.ReactNode;
  locale: string;
  messages: AbstractIntlMessages;
  nonce?: string;
}

export function Providers({
  children,
  locale,
  messages,
  nonce,
}: ProvidersProps) {
  const queryClient = getQueryClient();
  const isDevelopment = process.env.NODE_ENV !== "production";

  return (
    <NextIntlClientProvider locale={locale} messages={messages} timeZone="UTC">
      <ThemeProvider
        attribute="class"
        defaultTheme="light"
        disableTransitionOnChange
        nonce={nonce}
      >
        <TooltipProvider>
          <QueryClientProvider client={queryClient}>
            {children}
            <Toaster position="bottom-right" richColors closeButton />
            {isDevelopment ? (
              <ReactQueryDevtools initialIsOpen={false} />
            ) : null}
          </QueryClientProvider>
        </TooltipProvider>
      </ThemeProvider>
    </NextIntlClientProvider>
  );
}
