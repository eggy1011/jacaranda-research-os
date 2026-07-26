"use client";

import { useMutation } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { api } from "@/lib/api";
import { Button, Card, CardTitle, ErrorNote } from "@/components/ui";

export default function InvitesPage() {
  const t = useTranslations("auth");
  const [role, setRole] = useState("member");
  const [minted, setMinted] = useState<{ code: string; role: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mint = useMutation({
    mutationFn: () => api.createInvite(role),
    onSuccess: (data) => {
      setError(null);
      setMinted({ code: data.invite_code, role: data.role });
    },
    onError: (err: unknown) => setError(String(err)),
  });

  return (
    <div className="mx-auto max-w-lg">
      <Card>
        <CardTitle>{t("mintInvite")}</CardTitle>
        <div className="flex items-center gap-3">
          <select
            value={role}
            onChange={(event) => setRole(event.target.value)}
            className="rounded-lg border border-[#B7A3CB] px-3 py-2 text-sm"
          >
            <option value="member">{t("role.member")}</option>
            <option value="reviewer">{t("role.reviewer")}</option>
            <option value="admin">{t("role.admin")}</option>
          </select>
          <Button onClick={() => mint.mutate()} disabled={mint.isPending}>
            {t("mintInvite")}
          </Button>
        </div>
        {minted ? (
          <div className="mt-4 rounded-lg border border-[#B7A3CB]/50 bg-[#F7F5FA] p-3">
            <p className="text-xs text-slate-500">{t("inviteOnce")}</p>
            <p className="mt-1 font-mono text-lg text-[#34234F]">{minted.code}</p>
            <p className="text-xs text-slate-500">
              {t(`role.${minted.role}` as never)}
            </p>
          </div>
        ) : null}
        {error ? (
          <div className="mt-3">
            <ErrorNote>{error}</ErrorNote>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
