# NIRVAH — Frontend

Next.js 14 (App Router) + TypeScript + Tailwind + React Flow.

## Run

```bash
npm install
cp .env.example .env.local     # fill in the Google OAuth values when you have them
npm run dev                    # http://localhost:3000
```

## Env

| Var | Notes |
|---|---|
| `NEXTAUTH_URL` | `http://localhost:3000` in dev |
| `NEXTAUTH_SECRET` | `openssl rand -base64 32` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | redirect URI `http://localhost:3000/api/auth/callback/google` |
| `NEXT_PUBLIC_API_URL` | backend base URL, default `http://localhost:8000` |
| `NEXT_PUBLIC_ALLOWED_DOMAIN` | sign-in is rejected outside this domain |
| `NEXT_PUBLIC_USE_MOCKS` | `true` serves fixtures from `lib/mockData.ts`; flip to `false` for the real API |
| `NEXT_PUBLIC_MOCK_LIVE` | optional, mocks only — advances the demo workflow every few polls so the tracking page visibly updates |

While `NEXT_PUBLIC_USE_MOCKS=true` the home page also offers **Continue as demo student**, so
the whole app is walkable before OAuth credentials exist. That button disappears once mocks are off.

## Routes

| Route | What |
|---|---|
| `/` | sign in, or the student's request list |
| `/request` | chat submission |
| `/track/[id]` | DAG tracking, polls every 15s |
| `/approve/[token]?action=approve\|reject` | approver page, no login |
| `/admin` | password gate → policies (upload, publish, diff) and approver contacts |

## Integration

Everything network-facing lives in `lib/api.ts`. Set `NEXT_PUBLIC_USE_MOCKS=false`, walk each
route, and report shape mismatches to whoever owns the API rather than patching around them here.
