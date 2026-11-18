"use client";

import { useActionState } from "react";
import { sendMagicLink, type LoginState } from "./actions";

const initial: LoginState = {};

export default function LoginPage() {
  const [state, action, pending] = useActionState(sendMagicLink, initial);
  return (
    <main className="shell narrow">
      <h1>Вхід</h1>
      <p className="muted">Надішлемо посилання на email. Пароля не потрібно.</p>
      {state.sent ? (
        <p className="ok">Перевірте пошту: ми надіслали посилання для входу.</p>
      ) : (
        <form action={action} className="stack">
          <label>
            Email
            <input name="email" type="email" autoComplete="email" required placeholder="you@example.com" />
          </label>
          <button type="submit" disabled={pending}>{pending ? "Надсилаємо…" : "Надіслати посилання"}</button>
          {state.error && <p className="err">{state.error}</p>}
        </form>
      )}
    </main>
  );
}
