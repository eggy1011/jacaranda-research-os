"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api";
import { Button, Card, CardTitle, ErrorNote } from "@/components/ui";

export default function LoginPage() {
  const t = useTranslations("auth");
  const locale = useLocale();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: () =>
      mode === "login"
        ? api.login(email, password)
        : api.register(inviteCode.trim(), email, password),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["me"] });
      router.push(`/${locale}/projects`);
    },
    onError: (err: unknown) => setError(String(err)),
  });

  const inputClass =
    "w-full rounded-lg border border-[#B7A3CB] px-3 py-2 text-sm focus:border-[#563F7C] focus:outline-none";

  return (
    <div className="mx-auto max-w-md py-10">
      <Card>
        <CardTitle>{mode === "login" ? t("login") : t("register")}</CardTitle>
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            submit.mutate();
          }}
        >
          {mode === "register" ? (
            <input
              value={inviteCode}
              onChange={(event) => setInviteCode(event.target.value)}
              placeholder={t("inviteCode")}
              className={inputClass}
            />
          ) : null}
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder={t("email")}
            className={inputClass}
            autoComplete="email"
          />
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={t("password")}
            className={inputClass}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
          {mode === "register" ? (
            <p className="text-xs text-slate-500">{t("passwordHint")}</p>
          ) : null}
          <Button type="submit" disabled={submit.isPending || !email || !password}>
            {mode === "login" ? t("login") : t("register")}
          </Button>
        </form>
        {error ? (
          <div className="mt-3">
            <ErrorNote>{error}</ErrorNote>
          </div>
        ) : null}
        <button
          type="button"
          className="mt-4 text-sm text-[#563F7C] underline hover:text-[#34234F]"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError(null);
          }}
        >
          {mode === "login" ? t("switchToRegister") : t("switchToLogin")}
        </button>
      </Card>
    </div>
  );
}
