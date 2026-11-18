import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export type Role = "tenant" | "owner";

/** Returns the signed-in user and profile, or redirects to login / onboarding / the other cabinet. */
export async function requireProfile(role: Role) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const { data: profile } = await supabase
    .from("profiles")
    .select("id, role, name")
    .eq("id", user.id)
    .maybeSingle();
  if (!profile) redirect("/onboarding");
  if (profile.role !== role) redirect(profile.role === "tenant" ? "/tenant" : "/owner");
  return { supabase, user, profile };
}
