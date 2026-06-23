# SannySystem Operação Mobile

Aplicativo operacional em React Native com Expo para Android e iPhone.

## Funções

- Login com JWT do SannySystem.
- Login biométrico quando o aparelho possuir biometria cadastrada.
- Check-in com GPS.
- Check-out com GPS.
- Checklist offline.
- Fotos pela câmera integrada.
- Assinatura na tela.
- Ordens de serviço.
- Estoque.
- Ocorrências.
- Fila offline local com SQLite.
- Sincronização automática quando a conexão retorna.
- Upload automático para a API.
- Registro do dispositivo para notificações push.

## Configuração da API

Defina a URL da API antes de iniciar:

```bash
EXPO_PUBLIC_SANNY_API_URL="https://sua-api-sannysystem.com/api" npm run start
```

Para teste em rede local, o backend precisa escutar na rede:

```bash
SANNYSYSTEM_API_HOST=0.0.0.0
SANNYSYSTEM_API_PORT=3000
```

No celular, use:

```text
http://IP_DO_COMPUTADOR:3000/api
```

Não abra portas no roteador para teste local. Use apenas Wi-Fi interno ou uma API publicada com HTTPS.

## Desenvolvimento

```bash
npm install
npm run start
```

Depois, abra pelo Expo Go no Android ou iPhone.

## Builds

Para gerar builds empresariais, use EAS:

```bash
npx eas build --platform android
npx eas build --platform ios
```

Para push notifications remotas, configure o `projectId` do EAS em `app.json`.
