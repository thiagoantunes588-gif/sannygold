# SannyGold no Celular

Atualmente nao ha APK Android nem aplicativo iOS publicado para instalacao direta.
Nao existe arquivo `.apk` ou `.ipa` oficial nesta pasta.

O acesso pelo celular pode ser feito de duas formas:

1. Pelo navegador, usando o endereco mostrado no painel `Acesso pelo celular no Wi-Fi`.
2. Como atalho na tela inicial, quando o celular estiver na mesma rede do computador que roda o sistema.

## Android

1. Abra o Chrome no celular.
2. Acesse o endereco informado pelo sistema, por exemplo `http://IP_DO_COMPUTADOR:5007/`.
3. Faça login normalmente.
4. No menu do Chrome, use `Adicionar à tela inicial` ou `Instalar app`, se a opcao aparecer.

## iPhone / iOS

1. Abra o Safari no iPhone.
2. Acesse o endereco informado pelo sistema, por exemplo `http://IP_DO_COMPUTADOR:5007/`.
3. Faça login normalmente.
4. Toque em compartilhar e escolha `Adicionar à Tela de Início`.

## Status PWA

O sistema web ja possui `manifest.webmanifest` e `service-worker.js`, entao o navegador
pode oferecer instalacao como atalho/app da tela inicial. Isso nao substitui um APK ou
um app iOS publicado; e apenas o acesso web instalado no celular.
