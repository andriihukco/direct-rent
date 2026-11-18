import { requireProfile } from "@/lib/session";
import { saveTenantProfile, deleteTenantDoc } from "./actions";
import DocUpload from "./DocUpload";
import Link from "next/link";

const KINDS: Record<string, string> = {
  student_card: "Студентський квиток",
  income: "Довідка про доходи",
  employer: "Довідка з роботи",
  other: "Інше",
};

export default async function TenantPage() {
  const { supabase, user, profile } = await requireProfile("tenant");
  const { data: tp } = await supabase.from("tenant_profiles").select("*").eq("profile_id", user.id).maybeSingle();
  const { data: docs } = await supabase.from("tenant_docs").select("*").order("created_at", { ascending: false });

  return (
    <main className="shell">
      <header className="bar">
        <h1>Мій профіль</h1>
        <nav>
          <Link href="/tenant/listings">Оголошення</Link>
          <form action="/logout" method="post"><button className="ghost" type="submit">Вийти</button></form>
        </nav>
      </header>

      <section className="card">
        <h2>Про себе</h2>
        <p className="muted">Власники бачать цей профіль. Ми не показуємо ваш email чи телефон без вашого дозволу.</p>
        <form action={saveTenantProfile} className="stack">
          <label>Імʼя<input name="name" defaultValue={profile.name ?? ""} required /></label>
          <label>Чим займаєтесь<input name="occupation" defaultValue={tp?.occupation ?? ""} placeholder="Студент, ІТ, лікар…" /></label>
          <div className="row">
            <label>Коли заїжджаєте<input name="move_in" defaultValue={tp?.move_in ?? ""} placeholder="Одразу, за 2 тижні…" /></label>
            <label>Термін<input name="term" defaultValue={tp?.term ?? ""} placeholder="6–11 місяців / рік і більше" /></label>
          </div>
          <div className="row">
            <label>Людей<input name="people" type="number" min={1} max={10} defaultValue={tp?.people ?? 1} /></label>
            <label>Бюджет, ₴ на місяць<input name="budget_uah" type="number" min={1} defaultValue={tp?.budget_uah ?? ""} /></label>
          </div>
          <label className="check"><input type="checkbox" name="student" defaultChecked={tp?.student ?? false} /> Студент</label>
          <label className="check"><input type="checkbox" name="foreign_citizen" defaultChecked={tp?.foreign_citizen ?? false} /> Іноземець</label>
          <label className="check"><input type="checkbox" name="kids" defaultChecked={tp?.kids ?? false} /> Є діти</label>
          <label className="check"><input type="checkbox" name="pets" defaultChecked={tp?.pets ?? false} /> Є тварина</label>
          <label>Яка тварина<input name="pet_note" defaultValue={tp?.pet_note ?? ""} placeholder="кіт, собака середня…" /></label>
          <label>Кілька слів про себе<textarea name="about" rows={3} defaultValue={tp?.about ?? ""} /></label>
          <button type="submit">Зберегти профіль</button>
        </form>
        <p className="muted small">
          Підтвердження особи через Дію ще не підключене. Поки що профіль без позначки «перевірено».
        </p>
      </section>

      <section className="card">
        <h2>Документи</h2>
        <p className="muted">Видно лише вам. Власник побачить їх тільки після того, як ви погодитеся на перегляд.</p>
        {docs && docs.length > 0 ? (
          <ul className="list">
            {docs.map((d) => (
              <DocRow key={d.id} id={d.id} kind={KINDS[d.kind] ?? d.kind} path={d.storage_path} supabase={supabase} />
            ))}
          </ul>
        ) : (
          <p className="muted">Ще немає документів.</p>
        )}
        <DocUpload userId={user.id} />
      </section>
    </main>
  );
}

async function DocRow({ id, kind, path, supabase }: {
  id: number; kind: string; path: string;
  supabase: Awaited<ReturnType<typeof requireProfile>>["supabase"];
}) {
  const { data } = await supabase.storage.from("tenant-docs").createSignedUrl(path, 600);
  return (
    <li className="row-item">
      <span>{kind}</span>
      {data?.signedUrl && <a href={data.signedUrl} target="_blank" rel="noreferrer">Відкрити</a>}
      <form action={async () => { "use server"; await deleteTenantDoc(id); }}>
        <button className="ghost" type="submit">Видалити</button>
      </form>
    </li>
  );
}
