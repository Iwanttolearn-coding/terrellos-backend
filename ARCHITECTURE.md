# TM Dezigns Ecosystem — Architecture Map
# Last updated: 2026-05-20
# THIS IS THE CANONICAL REFERENCE. DO NOT DEVIATE.

## Backends
- terrellos-backend.fly.dev  → shared backend for ALL apps
  CORS origins:
    https://app.tm-dezigns.com       (TerrellOS)
    https://pastoraiconnect.com      (Pastor AI Connect)
    https://heavenlyeternalecho.com  (Heavenly Eternal Echo)
    http://localhost:5173
    http://localhost:3000

## Frontends
| App                    | Domain                        | Repo                  | App ID                |
|------------------------|-------------------------------|-----------------------|-----------------------|
| TerrellOS              | app.tm-dezigns.com            | terrellos-frontend    | terrellos             |
| Pastor AI Connect      | pastoraiconnect.com           | pastoraiconnect       | pastor-ai-connect     |
| Heavenly Eternal Echo  | heavenlyeternalecho.com       | eternal-echo          | heavenly-eternal-echo |

## Isolation Rules
- TerrellOS: NO Wix, NO Echo branding, NO Pastor AI branding
- Pastor AI: NO TerrellOS naming (except founder/admin), NO Echo branding, NO Wix
- Eternal Echo: Wix controls DNS/marketing. Cloudflare Pages for app frontend.
  NO TerrellOS branding, NO Pastor AI branding.

## LocalStorage Keys (MUST be unique per app)
- TerrellOS:  terrellos_user
- Pastor AI:  pastorai_user
- Echo:       hee_user

## Founder Emails (always super_admin everywhere)
- millzterrell210@icloud.com
- millzterrell5@gmail.com
