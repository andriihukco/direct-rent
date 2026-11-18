import { chooseRole } from "./actions";

export default function Onboarding() {
  return (
    <main className="shell narrow">
      <h1>Хто ви?</h1>
      <p className="muted">Роль обирається один раз. Її не можна змінити пізніше.</p>
      <form action={chooseRole} className="stack">
        <button name="role" value="tenant" type="submit">Шукаю житло</button>
        <button name="role" value="owner" type="submit" className="secondary">Здаю житло</button>
      </form>
    </main>
  );
}
