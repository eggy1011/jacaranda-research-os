import type { Metadata } from "next";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import type { ReactNode } from "react";

import { Providers } from "@/components/providers";
import { routing } from "@/i18n/routing";
import { LocaleSwitch } from "./locale-switch";
import { UserMenu } from "./user-menu";

import "../globals.css";

export const metadata: Metadata = {
  title: "Jacaranda Research OS",
  description: "Bilingual, source-grounded equity research.",
};

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) {
    notFound();
  }
  setRequestLocale(locale);
  const t = await getTranslations("nav");
  return (
    <html lang={locale === "zh" ? "zh-CN" : "en-AU"}>
      <body>
        <NextIntlClientProvider>
          <Providers>
        <div className="min-h-screen bg-[#F7F5FA] text-[#25232A]">
          <header className="border-b border-[#B7A3CB]/40 bg-white">
            <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
              <Link href={`/${locale}`} className="text-lg font-bold text-[#34234F]">
                {t("title")}
              </Link>
              <nav className="flex items-center gap-5 text-sm">
                <Link
                  href={`/${locale}/projects`}
                  className="font-medium text-[#563F7C] hover:text-[#34234F]"
                >
                  {t("projects")}
                </Link>
                <LocaleSwitch label={t("language")} />
                <UserMenu />
              </nav>
            </div>
          </header>
              <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
            </div>
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
