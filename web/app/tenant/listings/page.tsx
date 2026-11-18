import Link from "next/link";
import { requireProfile } from "@/lib/session";

export default async function TenantListings() {
  const { supabase } = await requireProfile("tenant");
  // RLS returns only listings that passed the bot's filter, and only to tenants.
  const { data: listings } = await supabase
    .from("listings")
    .select("id, text, price_uah, price_raw, rooms, district, street, pets, url, posted_at, verdict")
    .order("posted_at", { ascending: false })
    .limit(50);

  return (
    <main className="shell">
      <header className="bar">
        <h1>Оголошення від власників</h1>
        <nav><Link href="/tenant">Мій профіль</Link></nav>
      </header>
      {!listings || listings.length === 0 ? (
        <p className="muted">Поки немає оголошень. Щойно з&apos;являться нові, вони зʼявляться тут.</p>
      ) : (
        <ul className="list">
          {listings.map((l) => (
            <li key={l.id} className="card">
              <div className="price">{l.price_raw ?? (l.price_uah ? `${l.price_uah} ₴` : "ціна не вказана")}</div>
              <div className="muted">
                {l.rooms ? `${l.rooms === 3 ? "3+" : l.rooms}-кімн` : "кімнати не вказано"} · {l.district ?? "район не вказано"}
                {l.street ? ` · ${l.street}` : ""}
              </div>
              <p className="clamp">{l.text}</p>
              {l.verdict === "pass_unverified" && <p className="warn">Не перевірено автоматично</p>}
              <a href={l.url} target="_blank" rel="noreferrer">Оригінал оголошення</a>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
