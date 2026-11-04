import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { auth, errMsg } from "../services/api";
import { Btn, ErrorBox } from "../components/ui";

export default function Login() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [register, setRegister] = useState(false);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      if (register) await auth.register(email, password);
      await auth.login(email, password);
      nav("/");
    } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="flex min-h-screen items-center justify-center bg-green-950 p-4">
      <div className="w-full max-w-sm space-y-3 rounded-2xl bg-white p-6 shadow-xl">
        <h1 className="text-xl font-bold">🌱 GreenCloud AI 2.0</h1>
        <p className="text-xs text-slate-500">{register ? "The first account created becomes admin." : "Sign in to continue."}</p>
        <input className="w-full rounded-lg border px-3 py-2 text-sm" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input className="w-full rounded-lg border px-3 py-2 text-sm" type="password" placeholder="Password (min 8 chars)" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
        {err && <ErrorBox error={err} />}
        <Btn onClick={submit} disabled={busy || !email || password.length < 8} style={{ width: "100%" }}>{busy ? "…" : register ? "Create account" : "Sign in"}</Btn>
        <button className="w-full text-center text-xs text-green-700 underline" onClick={() => setRegister(!register)}>{register ? "Have an account? Sign in" : "No account? Register"}</button>
      </div>
    </div>
  );
}
