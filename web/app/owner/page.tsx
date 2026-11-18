import { requireProfile } from "@/lib/session";
import { addFlat, deleteFlat } from "./actions";
import PhotoUpload from "./PhotoUpload";
import { DISTRICTS, RULES } from "@/lib/options";

export default async function OwnerPage() {
  const { supabase, user } = await requireProfile("owner");
  const { data: flats } = await supabase.from("owner_flats").select("*").order("created_at", { ascending: false });

  return (
    <main className="shell">
      <header className="bar">
        <h1>Мої квартири</h1>
        <form action="/logout" method="post"><button className="ghost" type="submit">Вийти</button></form>
      </header>

      <section className="card">
        <h2>Нова квартира</h2>
        <form action={addFlat} className="stack">
          <label>Район
            <select name="district" required defaultValue="">
              <option value="" disabled>Оберіть район</option>
              {DISTRICTS.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </label>
          <div className="row">
            <label>Кімнат
              <select name="rooms" required defaultValue="2">
                <option value="1">1</option><option value="2">2</option><option value="3">3 і більше</option>
              </select>
            </label>
            <label>Ціна, ₴ на місяць<input name="price_uah" type="number" min={1} required /></label>
          </div>
          <fieldset>
            <legend>Кого готові поселити</legend>
            {RULES.map((r) => (
              <label key={r.id} className="check"><input type="checkbox" name="rules" value={r.id} /> {r.label}</label>
            ))}
          </fieldset>
          <label className="check"><input type="checkbox" name="contract_official" defaultChecked /> Офіційний договір</label>
          <button type="submit">Додати квартиру</button>
        </form>
      </section>

      {!flats || flats.length === 0 ? (
        <p className="muted">Ще немає квартир. Додайте першу вище.</p>
      ) : (
        <ul className="list">
          {await Promise.all(flats.map(async (f) => {
            const urls = await Promise.all(f.photo_paths.map(async (p: string) =>
              (await supabase.storage.from("listing-photos").createSignedUrl(p, 600)).data?.signedUrl));
            return (
              <li key={f.id} className="card">
                <div className="price">{f.price_uah} ₴ / міс</div>
                <div className="muted">{f.rooms === 3 ? "3+" : f.rooms}-кімн · {f.district}</div>
                <div className="why">{f.rules.map((r: string) => <span key={r} className="tag">{RULES.find((x) => x.id === r)?.label ?? r}</span>)}</div>
                <div className="photos">
                  {urls.filter(Boolean).map((u, i) => (
                    // eslint-disable-next-line @next/next/no-img-element -- signed Supabase URLs, not optimizable
                    <img key={i} src={u!} alt="" />
                  ))}
                </div>
                <PhotoUpload flatId={f.id} userId={user.id} />
                <form action={async () => { "use server"; await deleteFlat(f.id); }}>
                  <button className="ghost" type="submit">Видалити квартиру</button>
                </form>
              </li>
            );
          }))}
        </ul>
      )}
    </main>
  );
}
