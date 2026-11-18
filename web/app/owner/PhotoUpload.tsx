"use client";

import FileUpload from "@/components/FileUpload";
import { addFlatPhoto } from "./actions";

export default function PhotoUpload({ flatId, userId }: { flatId: number; userId: string }) {
  return (
    <FileUpload
      bucket="listing-photos"
      userId={userId}
      folder={String(flatId)}
      accept="image/jpeg,image/png,image/webp"
      label="Додати фото (JPG, PNG, до 10 МБ)"
      onUploaded={(path) => addFlatPhoto(flatId, path)}
    />
  );
}
