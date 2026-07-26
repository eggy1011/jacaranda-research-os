"use client";

import { useLocale } from "next-intl";
import { usePathname, useRouter } from "next/navigation";

export function LocaleSwitch({ label }: { label: string }) {
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const other = locale === "zh" ? "en" : "zh";

  function toggle() {
    const segments = pathname.split("/");
    segments[1] = other;
    router.push(segments.join("/") || `/${other}`);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="rounded-lg border border-[#B7A3CB] px-3 py-1 text-sm text-[#563F7C] hover:bg-[#F7F5FA]"
    >
      {label}
    </button>
  );
}
