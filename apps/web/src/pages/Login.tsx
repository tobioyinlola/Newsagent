import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { DEV_AUTH, devSignIn } from "../lib/auth";
import { Button, Card, Field, inputCls, Notice } from "../components/ui";

export function Login() {
  const [email, setEmail] = useState("");
  const nav = useNavigate();
  const [params] = useSearchParams();
  const invite = params.get("invite");
  return (
    <div className="mx-auto max-w-md space-y-4 p-6">
      <h1 className="text-2xl font-extrabold text-blue-900">Newsagent</h1>
      <Card title="Sign in">
        {DEV_AUTH ? (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              devSignIn(email);
              nav(invite ? `/redeem?code=${encodeURIComponent(invite)}` : "/projects");
            }}
          >
            <Notice tone="warn">Development sign-in. A real email sign-in replaces this once the auth provider is chosen.</Notice>
            <Field label="Email">{(id) => <input id={id} type="email" required className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
            <Button type="submit">Continue</Button>
          </form>
        ) : (
          <Notice tone="warn">Sign-in is not configured for this environment yet.</Notice>
        )}
      </Card>
      <p className="text-sm text-slate-600">Invite-only pilot. Have an invite code? Sign in with the invited email and you will be asked for it.</p>
    </div>
  );
}
