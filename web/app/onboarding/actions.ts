"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export async function chooseRole(formData: FormData) {
  const role = String(formData.get("role") ?? "");
  if (role !== "tenant" && role !== "owner") return;
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  // Insert only: the role is fixed after onboarding (see the profiles_role_fixed trigger).
  const { error } = await supabase.from("profiles").insert({ id: user.id, role });
  if (error) redirect("/");
  if (role === "tenant") await supabase.from("tenant_profiles").insert({ profile_id: user.id });
  redirect(role === "tenant" ? "/tenant" : "/owner");
}
