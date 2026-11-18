"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/browser";

type Props = {
  bucket: "listing-photos" | "tenant-docs";
  userId: string;
  /** Extra folder segment, e.g. a flat id. Files are stored under <userId>/<folder>/… */
  folder?: string;
  accept: string;
  label: string;
  /** Called with the storage path after a successful upload. */
  onUploaded: (path: string) => Promise<void>;
};

/** Uploads straight to Supabase Storage with the user's session (RLS checks the folder). */
export default function FileUpload({ bucket, userId, folder, accept, label, onUploaded }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    const supabase = createClient();
    const safe = file.name.replace(/[^\w.\-]+/g, "_").slice(-80);
    const path = [userId, folder, `${crypto.randomUUID()}-${safe}`].filter(Boolean).join("/");
    const { error: upErr } = await supabase.storage.from(bucket).upload(path, file, { contentType: file.type });
    if (upErr) {
      setError(upErr.message.includes("too large") ? "Файл завеликий, до 10 МБ" : "Не вдалося завантажити файл");
    } else {
      await onUploaded(path);
    }
    setBusy(false);
    e.target.value = "";
  }

  return (
    <label className="upload">
      <span>{busy ? "Завантажуємо…" : label}</span>
      <input type="file" accept={accept} onChange={onChange} disabled={busy} />
      {error && <span className="err">{error}</span>}
    </label>
  );
}
