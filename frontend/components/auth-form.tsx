"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { api, User } from "@/lib/api";

const schema = z.object({ name: z.string().trim().min(1, "Enter your name").max(100).optional(), email: z.string().email("Enter a valid email address"), password: z.string().min(12, "Use at least 12 characters").max(128), confirm: z.string().optional() }).refine((v) => v.name || !v.confirm || v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match" });
type Values = z.infer<typeof schema>;

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [serverError, setServerError] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Values>({ resolver: zodResolver(schema) });
  const submit = async (values: Values) => {
    setServerError("");
    try {
      const body = mode === "register" ? { name: values.name, email: values.email, password: values.password } : { email: values.email, password: values.password };
      await api<User>(`/auth/${mode}`, { method: "POST", body: JSON.stringify(body) });
      router.push("/app"); router.refresh();
    } catch (error) { setServerError(error instanceof Error ? error.message : "Unable to authenticate."); }
  };
  const input = "w-full rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/10";
  return <form onSubmit={handleSubmit(submit)} className="space-y-4">
    {mode === "register" && <label className="block text-sm font-medium">Full name<input className={`${input} mt-2`} autoComplete="name" placeholder="Alex Morgan" {...register("name")} />{errors.name && <span className="mt-1 block text-xs text-red-600">{errors.name.message}</span>}</label>}
    <label className="block text-sm font-medium">Work email<input className={`${input} mt-2`} type="email" autoComplete="email" placeholder="you@company.com" {...register("email")} />{errors.email && <span className="mt-1 block text-xs text-red-600">{errors.email.message}</span>}</label>
    <label className="block text-sm font-medium">Password<div className="relative mt-2"><input className={`${input} pr-16`} type={visible ? "text" : "password"} autoComplete={mode === "login" ? "current-password" : "new-password"} placeholder="At least 12 characters" {...register("password")} /><button type="button" onClick={() => setVisible(!visible)} className="absolute inset-y-0 right-3 text-xs text-muted">{visible ? "Hide" : "Show"}</button></div>{errors.password && <span className="mt-1 block text-xs text-red-600">{errors.password.message}</span>}</label>
    {mode === "register" && <label className="block text-sm font-medium">Confirm password<input className={`${input} mt-2`} type={visible ? "text" : "password"} autoComplete="new-password" {...register("confirm")} />{errors.confirm && <span className="mt-1 block text-xs text-red-600">{errors.confirm.message}</span>}</label>}
    {serverError && <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{serverError}</p>}
    <button disabled={isSubmitting} className="w-full rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#116a57] disabled:opacity-60">{isSubmitting ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
    <p className="pt-1 text-center text-sm text-muted">{mode === "login" ? "New to Northstar? " : "Already have an account? "}<Link className="font-semibold text-brand hover:underline" href={mode === "login" ? "/register" : "/login"}>{mode === "login" ? "Create an account" : "Sign in"}</Link></p>
  </form>;
}
