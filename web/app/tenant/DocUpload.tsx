"use client";

import { useState } from "react";
import FileUpload from "@/components/FileUpload";
import { recordTenantDoc } from "./actions";

export default function DocUpload({ userId }: { userId: string }) {
  const [kind, setKind] = useState("student_card");
  return (
    <div className="stack">
      <label>
        Тип документа
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="student_card">Студентський квиток</option>
          <option value="income">Довідка про доходи</option>
          <option value="employer">Довідка з роботи</option>
          <option value="other">Інше</option>
        </select>
      </label>
      <FileUpload
        bucket="tenant-docs"
        userId={userId}
        accept="image/jpeg,image/png,image/webp,application/pdf"
        label="Обрати файл (JPG, PNG, PDF, до 10 МБ)"
        onUploaded={(path) => recordTenantDoc(kind, path)}
      />
    </div>
  );
}
