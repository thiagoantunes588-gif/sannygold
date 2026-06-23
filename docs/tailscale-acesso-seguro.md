# Acesso Externo Seguro com Tailscale

Este guia explica como acessar o sistema SannyGold pelo celular fora da empresa sem publicar o sistema na internet.

Use este modo apenas para pessoas autorizadas. O login do sistema continua obrigatório.

## O Que É

O Tailscale cria uma rede privada entre o computador servidor e o celular do Thiago. O acesso acontece por um IP privado do Tailscale, normalmente começando com `100.`.

Isso é diferente de abrir porta no roteador. Não use redirecionamento de porta, DMZ, `tailscale funnel` ou link público para este sistema.

## Instalar no Computador Servidor

1. Acesse `https://tailscale.com/download`.
2. Baixe e instale o Tailscale para macOS ou Windows.
3. Abra o Tailscale.
4. Entre com a conta escolhida para a empresa.
5. Confirme que o computador aparece como conectado.

No Mac, se o comando estiver disponível, confira pelo Terminal:

```bash
tailscale status
tailscale ip -4
```

O comando `tailscale ip -4` mostra o IP privado do computador. Exemplo:

```text
100.101.102.103
```

## Instalar no Celular

1. Instale o app Tailscale pela App Store ou Google Play.
2. Entre na mesma conta/rede Tailscale usada no computador servidor.
3. Ative a conexão no app.
4. Confirme que o computador servidor aparece na lista de dispositivos.

Computador e celular precisam estar na mesma conta/rede Tailscale.

## Abrir o Sistema pelo Celular

1. Inicie a SannyGold no computador pelo launcher ou pelo script:

```bash
bash scripts/start_tailscale_secure.sh
```

2. Veja o IP Tailscale do computador:

```bash
tailscale ip -4
```

3. No celular, com o Tailscale ligado, abra:

```text
http://IP_TAILSCALE:5007
```

Exemplo:

```text
http://100.101.102.103:5007
```

4. Entre no sistema com usuário e senha normalmente.

## Mostrar a URL no Painel Admin

Para exibir o endereço Tailscale na tela `Acesso pelo Celular`, configure uma destas variáveis no `.env.local`:

```bash
SANNYGOLD_TAILSCALE_URL=http://100.101.102.103:5007/
```

ou:

```bash
SANNYGOLD_TAILSCALE_IP=100.101.102.103
```

Depois reinicie o launcher da SannyGold.

## Segurança Obrigatória

- Não compartilhe o IP Tailscale com pessoas fora da equipe autorizada.
- Não use `tailscale funnel` para este sistema.
- Não abra portas no roteador da empresa.
- Use senhas fortes no sistema SannyGold.
- Mantenha o backup local e Dropbox ativo.
- Revise usuários e perfis periodicamente.
- Remova do Tailscale qualquer celular ou computador que não deve mais acessar.

## Diferença Entre Wi-Fi Local e Tailscale

Wi-Fi local:

- Funciona quando o celular está na mesma rede da empresa.
- Usa endereço como `http://192.168.x.x:5007`.
- Não funciona fora da empresa.

Tailscale:

- Funciona de fora da empresa quando o celular está conectado ao Tailscale.
- Usa endereço como `http://100.x.x.x:5007`.
- Continua privado, sem abrir o sistema publicamente.

## Se Não Abrir

1. Confira se o computador servidor está ligado.
2. Confira se o launcher da SannyGold está aberto.
3. Confira se o Tailscale está conectado no computador e no celular.
4. Confira se ambos estão na mesma conta/rede Tailscale.
5. Confira se a URL usa `http://` e a porta correta, por padrão `5007`.
6. Verifique se o firewall do computador não bloqueou Python/Waitress.
