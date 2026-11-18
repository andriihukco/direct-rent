"use server";

import { revalidatePath } from "next/cache";
import { requireProfile } from "@/lib/session";

const str = (f: FormData, k: string) => String(f.get(k) ?? "").trim() || null;
const bool = (f: FormData, k: string) => f.get(k) === "on";

export async function saveTenantProfile(formData: FormData) {
  const { supabase, user } = await requireProfile("tenant");
  const budget = Number(formData.get("budget_uah"));
  const people = Math.min(Math.max(Number(formData.get("people")) || 1, 1), 10);
  await supabase.from("profiles").update({ name: str(formData, "name") }).eq("id", user.id);
  await supabase.from("tenant_profiles").upsert({
    profile_id: user.id,
    occupation: str(formData, "occupation"),
    move_in: str(formData, "move_in"),
    term: str(formData, "term"),
    people,
    pets: bool(formData, "pets"),
    pet_note: str(formData, "pet_note"),
    kids: bool(formData, "kids"),
    student: bool(formData, "student"),
    foreign_citizen: bool(formData, "foreign_citizen"),
    budget_uah: budget > 0 ? Math.round(budget) : null,
    about: str(formData, "about"),
    updated_at: new Date().toISOString(),
  });
  revalidatePath("/tenant");
}

export async function recordTenantDoc(kind: string, storagePath: string) {
  const { supabase, user } = await requireProfile("tenant");
  if (!storagePath.startsWith(`${user.id}/`)) throw new Error("bad path");
  await supabase.from("tenant_docs").insert({ tenant_id: user.id, kind, storage_path: storagePath });
  revalidatePath("/tenant");
}

export async function deleteTenantDoc(id: number) {
  const { supabase, user } = await requireProfile("tenant");
  const { data: doc } = await supabase.from("tenant_docs").select("storage_path").eq("id", id).maybeSingle();
  if (!doc || !doc.storage_path.startsWith(`${user.id}/`)) return;
  await supabase.storage.from("tenant-docs").remove([doc.storage_path]);
  await supabase.from("tenant_docs").delete().eq("id", id);
  revalidatePath("/tenant");
}
