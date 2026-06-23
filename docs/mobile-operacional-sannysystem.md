# SannySystem - Aplicativo mobile operacional

## Objetivo

O aplicativo mobile permite que equipes de operação trabalhem pelo celular em eventos, logística e estrutura, com funcionamento online/offline.

## Tecnologia

- React Native.
- Expo.
- Android.
- iPhone.
- SQLite local para fila offline.
- SecureStore para sessão.
- Expo Camera para fotos.
- Expo Location para GPS.
- Expo Notifications para push.
- Expo Local Authentication para biometria.

## Pasta do app

```text
mobile/
```

Principais arquivos:

- `mobile/app/index.tsx`: tela operacional principal.
- `mobile/src/services/offline-store.ts`: cache e fila local.
- `mobile/src/services/sync-engine.ts`: sincronização automática.
- `mobile/src/services/api.ts`: comunicação com API SannySystem.
- `mobile/src/services/device-capabilities.ts`: câmera, GPS, assinatura e notificações.
- `mobile/src/components/camera-capture.tsx`: câmera integrada.
- `mobile/src/components/signature-pad.tsx`: assinatura.

## Fluxo operacional

1. Usuário entra com login e senha.
2. O app salva sessão segura.
3. Se houver biometria, o próximo acesso pode ser liberado com Face ID, Touch ID ou biometria Android.
4. O app baixa ordens de serviço e guarda cache local.
5. A equipe registra checklist, check-in, check-out, fotos, assinatura, estoque e ocorrências.
6. Sem internet, as ações entram na fila SQLite local.
7. Quando a internet volta, a fila é enviada para a API.
8. O backend grava em PostgreSQL e processa conflitos.
9. O app mostra fila, falhas e status de conexão.

## API necessária

O mobile usa os endpoints já criados no desktop/backend:

- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/service-orders`
- `POST /api/offline/queue`
- `POST /api/offline/sync`
- `POST /api/mobile/devices`

## Configuração para rede local

Por padrão, o backend desktop escuta somente localmente.

Para teste em Wi-Fi interno:

```bash
SANNYSYSTEM_API_HOST=0.0.0.0
SANNYSYSTEM_API_PORT=3000
```

No aplicativo, configure:

```text
http://IP_DO_COMPUTADOR:3000/api
```

Para operação empresarial real, prefira API publicada com HTTPS.

## Segurança

- Tokens ficam no SecureStore do dispositivo.
- Dados offline ficam no SQLite local do aplicativo.
- Fotos e assinaturas ficam na fila local até sincronizar.
- A sincronização usa JWT.
- O dispositivo registra push token em `AppSetting` no backend.
- A API deve ficar em HTTPS fora de rede local.

## Notificações push

O app já solicita permissão e registra token Expo quando houver `projectId` do EAS configurado em `mobile/app.json`.

Para produção:

1. Criar projeto EAS.
2. Preencher `expo.extra.eas.projectId`.
3. Configurar credenciais Apple/Google.
4. Usar `POST /api/mobile/devices` para guardar tokens.
5. Enviar notificações por serviço backend dedicado ou Expo Push API.

## Build Android/iPhone

Desenvolvimento:

```bash
cd mobile
npm install
npm run start
```

Build Android:

```bash
npx eas build --platform android
```

Build iPhone:

```bash
npx eas build --platform ios
```

O build iOS exige conta Apple Developer.
