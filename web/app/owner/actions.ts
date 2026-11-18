"use server";

import { revalidatePath } from "next/cache";
import { requireProfile } from "@/lib/session";
import { DISTRICTS, RULES } from "@/lib/options";

const str = (f: FormData, k: string) => String(f.get(k) ?? "").trim() || null;

export async function addFlat(formData: FormData) {
  const { supabase, user } = await requireProfile("owner");
  const district = str(formData, "district");
  const rooms = Number(formData.get("rooms"));
  const price = Number(formData.get("price_uah"));
  if (!district || !(DISTRICTS as readonly string[]).includes(district)) return;
  if (!(rooms >= 1 && rooms <= 3) || !(price > 0)) return;
  const rules = formData.getAll("rules").map(String).filter((r) => RULES.some((x) => x.id === r));
  await supabase.from("owner_flats").insert({
    owner_id: user.id,
    district,
    rooms,
    price_uah: Math.round(price),
    rules,
    contract_official: formData.get("contract_official") === "on",
  });
  revalidatePath("/owner");
}

export async function addFlatPhoto(flatId: number, storagePath: string) {
  const { supabase, user } = await requireProfile("owner");
  if (!storagePath.startsWith(`${user.id}/${flatId}/`)) throw new Error("bad path");
  const { data: flat } = await supabase.from("owner_flats").select("photo_paths").eq("id", flatId).maybeSingle();
  if (!flat) return;
  await supabase.from("owner_flats").update({ photo_paths: [...flat.photo_paths, storagePath].slice(0, 10) }).eq("id", flatId);
  revalidatePath("/owner");
}

export async function deleteFlat(flatId: number) {
  const { supabase, user } = await requireProfile("owner");
  const { data: flat } = await supabase.from("owner_flats").select("photo_paths").eq("id", flatId).maybeSingle();
  if (!flat) return;
  if (flat.photo_paths.length) await supabase.storage.from("listing-photos").remove(flat.photo_paths);
  await supabase.from("owner_flats").delete().eq("id", flatId).eq("owner_id", user.id);
  revalidatePath("/owner");
}
