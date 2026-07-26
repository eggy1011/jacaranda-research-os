"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { api, ApiError } from "@/lib/api";

export function UserMenu() {
  const t = useTranslations("auth");
  const locale = useLocale();
  const router = useRouter();
  const queryClient = useQueryClient();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 1,
  });
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["me"] });
      router.push(`/${locale}/login`);
    },
  });

  if (me.data) {
    return (
      <span className="flex items-center gap-3 text-sm">
        {me.data.role === "admin" ? (
          <Link
            href={`/${locale}/admin/invites`}
            className="font-medium text-[#563F7C] hover:text-[#34234F]"
          >
            {t("invites")}
          </Link>
        ) : null}
        <span className="text-slate-500">
          {me.data.email} · {t(`role.${me.data.role}` as never)}
        </span>
        <button
          type="button"
          onClick={() => logout.mutate()}
          className="rounded-lg border border-[#B7A3CB] px-3 py-1 text-sm text-[#563F7C] hover:bg-[#F7F5FA]"
        >
          {t("logout")}
        </button>
      </span>
    );
  }
  return (
    <Link
      href={`/${locale}/login`}
      className="rounded-lg border border-[#B7A3CB] px-3 py-1 text-sm font-medium text-[#563F7C] hover:bg-[#F7F5FA]"
    >
      {t("login")}
    </Link>
  );
}
