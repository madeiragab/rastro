# Manual de instalação do Rastro 🐮

Do zero até o APK no celular: rodar na sua máquina, ligar o Firebase, publicar
na nuvem e gerar o app Android. No fim há uma seção grande de **erros comuns**.

> Os comandos estão em **PowerShell** (Windows). No Linux/macOS funcionam
> iguais, trocando `.\gradlew.bat` por `./gradlew` e `$env:VAR="x"` por
> `export VAR=x`.

---

## Atalho: só instalar e mostrar (APK de demonstração)

O **`Rastro-demo.apk`** da página de
[Releases](https://github.com/madeiragab/rastro/releases) funciona **sozinho
no celular**: sem servidor, sem PC e sem Firebase. Ele traz junto:

- um **banco SQLite** dentro do app, com a fazenda, os 2 pastos e os 14
  animais. O que você muda (pastos novos, alertas, contas da equipe) fica
  salvo mesmo depois de fechar o app;
- o **simulador** do rebanho e as mesmas regras de alerta da API (geocerca,
  imobilidade, perda de sinal).

Instale ([seção 11](#11-instalar-o-apk-no-celular)), abra e toque em
**Entrar**: a conta já vem preenchida (`produtor@rastro.com.br` /
`rastro2026`). Para demonstrar, escolha um animal na aba **Rebanho**, vá em
**Simular › Fugir do pasto** e, em ~25 s, o alerta aparece e o celular vibra.

> O fundo do mapa (ruas) vem da internet. Sem internet, o rebanho e os pastos
> aparecem do mesmo jeito, mas sobre um fundo cinza.

Para gerar de novo:

```powershell
cd frontend
```

```powershell
npm run build -- --mode demo
```

```powershell
npx cap sync android
```

```powershell
cd android; .\gradlew.bat assembleRelease
```

O modo vem do arquivo `frontend/.env.demo` (`VITE_MODO_DEMO=1`). O código fica
em `frontend/src/demo/`: `banco.ts` (SQLite), `simulador.ts` (regras) e
`servidor.ts` (as rotas da API respondidas no aparelho).

## Atalho: seu PC como servidor, acessível de qualquer lugar

O script `hospedar.ps1` coloca o Rastro no ar usando o seu PC. Ele sobe o
servidor e abre um túnel da Cloudflare com um endereço `https://` público, que
funciona no 4G ou em qualquer Wi-Fi. Não precisa de conta nem de abrir porta
no roteador. Depois ele gera o APK já apontando para esse endereço.

Instale uma vez (o Docker pede para reiniciar o PC):

```powershell
winget install Docker.DockerDesktop
```

```powershell
winget install Cloudflare.cloudflared
```

Abra o Docker Desktop, espere ficar verde e, na pasta do projeto:

```powershell
.\hospedar.ps1
```

No fim ele mostra o endereço público, o login inicial e o caminho do
`Rastro-online.apk`. Instale esse APK no celular ([seção 11](#11-instalar-o-apk-no-celular)).

- **Deixe o PC ligado e a janela aberta**: fechou, saiu do ar.
- **O endereço muda cada vez que você roda o script**, então instale o APK novo
  que ele gera. Para um endereço fixo, crie uma conta grátis no ngrok ou use um
  túnel com nome da Cloudflare (precisa de domínio).
- Se o PowerShell recusar rodar o script, libere só para esta janela:
  `Set-ExecutionPolicy -Scope Process Bypass`.

## Atalho: mostrar no celular numa apresentação (sem internet)

Use o **`Rastro-demo-hotspot.apk`** da página de
[Releases](https://github.com/madeiragab/rastro/releases). Ele não precisa de
Firebase nem de nuvem: o servidor roda no notebook, e o celular se conecta no
hotspot do notebook. No hotspot do Windows o notebook tem sempre o endereço
`192.168.137.1`, e é nele que esse APK procura o servidor.

1. No notebook, instale o Docker Desktop ([seção 2](#2-pré-requisitos)) e suba
   o Rastro **com internet** pelo menos uma vez (baixa as imagens):
   ```powershell
   docker compose up --build
   ```
2. Pegue o e-mail e a senha no bloco `ACESSO INICIAL` ([seção 3.2](#32-subir-tudo-com-docker-jeito-recomendado)).
3. Libere a porta no firewall (PowerShell **como administrador**, uma vez só):
   ```powershell
   New-NetFirewallRule -DisplayName "Rastro demo" -Direction Inbound -Protocol TCP -LocalPort 5173 -Action Allow -Profile Any
   ```
4. Ligue o hotspot: **Configurações › Rede e Internet › Hotspot móvel › Ligar**.
5. No celular: conecte no Wi-Fi do hotspot, instale o APK
   ([seção 11](#11-instalar-o-apk-no-celular)) e abra o Rastro.
6. Entre com o e-mail e a senha. Na aba **Simular**, escolha um animal e toque
   em **Fugir do pasto**: em ~25 s aparece o alerta.

> O mapa (ruas e satélite) vem da internet. Se o notebook estiver sem
> internet, o app funciona, mas o fundo do mapa fica cinza.

Se não conectar, abra `http://192.168.137.1:5173` no navegador do celular. Se
também não abrir, o problema é do notebook (Docker parado ou firewall), não do
APK.

---

## Sumário

1. [Como o Rastro é montado](#1-como-o-rastro-é-montado)
2. [Pré-requisitos](#2-pré-requisitos)
3. [Rodar na sua máquina](#3-rodar-na-sua-máquina)
4. [Rodar os testes](#4-rodar-os-testes)
5. [Abrir no celular pela rede local](#5-abrir-no-celular-pela-rede-local)
6. [APK de desenvolvimento (sem Firebase)](#6-apk-de-desenvolvimento-sem-firebase)
7. [Criar o projeto no Firebase](#7-criar-o-projeto-no-firebase)
8. [Publicar a API no Cloud Run](#8-publicar-a-api-no-cloud-run)
9. [Publicar o site no Firebase Hosting](#9-publicar-o-site-no-firebase-hosting)
10. [APK de produção (com Firebase)](#10-apk-de-produção-com-firebase)
11. [Instalar o APK no celular](#11-instalar-o-apk-no-celular)
12. [Lançar uma versão nova](#12-lançar-uma-versão-nova)
13. [Erros comuns](#13-erros-comuns)
14. [Cola de comandos](#14-cola-de-comandos)

---

## 1. Como o Rastro é montado

```
┌──────────────┐     ┌─────────────────────────┐     ┌──────────────────┐
│  App Android │     │  Firebase Hosting       │     │  Cloud Run       │
│  (APK)       │────▶│  site React + /api/** ──┼────▶│  API FastAPI     │──▶ PostgreSQL
│  Navegador   │     │  reescrito p/ Cloud Run │     │  (Python)        │    + PostGIS
└──────┬───────┘     └─────────────────────────┘     └────────┬─────────┘
       │                                                      │
       │  login (e-mail/senha)          ┌───────────────┐     │ alerta
       └───────────────────────────────▶│   Firebase    │◀────┘ (FCM)
          push, crashes, métricas       │ Auth · FCM ·  │
                                        │ Crashlytics · │
                                        │ Analytics     │
                                        └───────────────┘
```

| Peça | O que faz | Onde fica no código |
|---|---|---|
| **API** | regras de geocerca, alertas, simulador, usuários | `backend/` |
| **Frontend** | mapa, rebanho, alertas (React + Vite) | `frontend/src/` |
| **App Android** | o frontend empacotado com Capacitor | `frontend/android/` |
| **Banco** | Postgres com a extensão PostGIS (geometria) | — |

### Os dois modos de login

A API tem uma chave, `AUTH_MODO`:

| | `local` (padrão) | `firebase` |
|---|---|---|
| Quem guarda a senha | a própria API (Argon2id) | o Firebase Authentication |
| Sessão | cookie HttpOnly + token de 15 min | token do Firebase (renovado pelo SDK) |
| Recuperar senha | e-mail enviado pela API (precisa SMTP) | e-mail enviado pelo Firebase |
| Serve para | rodar na máquina, Docker, servidor próprio | **APK** e Firebase Hosting |

**O app e a API precisam estar no mesmo modo.** O app sabe qual é pelo build:
com as variáveis `VITE_FIREBASE_*` preenchidas ele usa Firebase, sem elas usa o
local. Se os dois discordarem, a tela de login avisa: *"Configuração
incompatível"*.

> **Por que o APK exige o modo Firebase?** O app instalado roda na origem
> `https://localhost`, e a API está em outro endereço. O cookie de sessão do
> modo local é `SameSite=strict` (proteção contra CSRF) e não atravessa
> origens. O token do Firebase vai num header, e header atravessa.

### O que é papel do Rastro e o que é papel do Firebase

O Firebase diz **quem** a pessoa é. **O que** ela pode fazer (dono, operador,
leitura) e **de qual fazenda** ela é continuam na tabela `usuarios` da API.
Ter conta no Firebase do projeto não dá acesso a nada sem cadastro no Rastro.

---

## 2. Pré-requisitos

| Ferramenta | Versão | Para quê | Como conferir |
|---|---|---|---|
| Git | qualquer | baixar o código | `git --version` |
| Docker Desktop | 4.x, com WSL2 | rodar API + banco na máquina | `docker info` |
| Node.js | **20 ou mais** | frontend e Capacitor | `node -v` |
| Python | 3.12 | rodar a API/testes fora do Docker | `python --version` |
| JDK | **17** (exatamente) | compilar o Android | `java -version` |
| Android SDK | plataforma 34 + build-tools | compilar o Android | ver abaixo |
| Firebase CLI | 13+ | publicar o Hosting | `firebase --version` |
| Google Cloud CLI | recente | publicar a API no Cloud Run | `gcloud --version` |

### Instalando no Windows

```powershell
winget install Git.Git
winget install Docker.DockerDesktop
winget install OpenJS.NodeJS.LTS
winget install Python.Python.3.12
winget install EclipseAdoptium.Temurin.17.JDK
winget install Google.AndroidStudio
winget install Google.CloudSDK
```

```powershell
npm install -g firebase-tools
```

Depois de instalar o **Android Studio**, abra ele uma vez e deixe o assistente
baixar o SDK. Em *More Actions › SDK Manager* confirme:

- **SDK Platforms**: Android 14 (API 34)
- **SDK Tools**: Android SDK Build-Tools, Android SDK Platform-Tools, Android SDK Command-line Tools

E configure as variáveis de ambiente (feche e abra o terminal depois):

```powershell
[Environment]::SetEnvironmentVariable("ANDROID_HOME", "$env:LOCALAPPDATA\Android\Sdk", "User")
```

```powershell
[Environment]::SetEnvironmentVariable("JAVA_HOME", "C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot", "User")
```

> Ajuste o caminho do `JAVA_HOME` para a pasta que existe na sua máquina
> (`dir "C:\Program Files\Eclipse Adoptium"`).

> **Docker no Windows precisa do WSL2.** Se `docker info` disser
> `no virtualization available`, rode `wsl --install` num PowerShell **como
> administrador**, reinicie o PC e abra o Docker Desktop de novo.

---

## 3. Rodar na sua máquina

### 3.1 Baixar o código

```powershell
git clone https://github.com/madeiragab/rastro.git
```

```powershell
cd rastro
```

> **Windows: use uma pasta de caminho curto** (ex.: `C:\dev\rastro`). O build
> do Android cria caminhos muito compridos e o Windows tem limite de 260
> caracteres — ver [erro "Filename too long"](#erros-do-android--gradle).

### 3.2 Subir tudo com Docker (jeito recomendado)

```powershell
docker compose up --build
```

Na primeira vez demora alguns minutos (baixa as imagens). Quando parar de
rolar log, abra:

| O quê | Endereço |
|---|---|
| App | http://localhost:5173 |
| Documentação da API (Swagger) | http://localhost:8000/docs |
| Banco | `127.0.0.1:5432` (usuário/senha `rastro`) |

**A senha inicial aparece no log uma vez só.** Procure o bloco
`ACESSO INICIAL`:

```powershell
docker compose logs api | Select-String -Context 0,12 "ACESSO INICIAL"
```

Ele traz o e-mail (`produtor@rastro.com.br`), a senha sorteada e a chave de
gateway. Perdeu? Zere tudo e suba de novo:

```powershell
docker compose down -v
```

```powershell
docker compose up --build
```

### 3.3 Demonstração

Na aba **Simular**, escolha um animal e:

| Botão | O que acontece |
|---|---|
| Fugir do pasto | o animal sai da cerca; alerta em ~25 s |
| Ficar parado | atividade zera; alerta em 90 s |
| Perder sinal | brinco para de transmitir; alerta em 60 s |
| Pastando | volta ao normal; alertas se resolvem sozinhos |

### 3.4 Rodar sem Docker (avançado)

Só vale se você já tem um Postgres com PostGIS instalado.

```powershell
cd backend
```

```powershell
python -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
```

```powershell
pip install -r requirements-dev.txt
```

```powershell
$env:DATABASE_URL="postgresql+psycopg://rastro:rastro@localhost:5432/rastro"; uvicorn app.main:app --reload --port 8000
```

Em outro terminal:

```powershell
cd frontend
```

```powershell
npm install
```

```powershell
npm run dev
```

---

## 4. Rodar os testes

Os testes usam **PostGIS de verdade** (o compose sobe um). Com o banco no ar:

```powershell
docker compose exec db psql -U rastro -c "CREATE DATABASE rastro_test"
```

```powershell
cd backend
```

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://rastro:rastro@localhost:5432/rastro_test"; pytest
```

Frontend (checagem de tipos + build):

```powershell
cd frontend
```

```powershell
npm run build
```

O GitHub Actions roda os dois a cada push (`.github/workflows/ci.yml`).

---

## 5. Abrir no celular pela rede local

1. Celular e PC no **mesmo Wi-Fi**.
2. Descubra o IP do PC: `ipconfig` → *Endereço IPv4* (ex.: `192.168.0.10`).
3. No celular, abra `http://192.168.0.10:5173`.
4. No Chrome: menu ⋮ → **Adicionar à tela inicial**.

Se não abrir, é quase sempre o **Firewall do Windows**. Libere a porta 5173 no
PowerShell **como administrador**:

```powershell
New-NetFirewallRule -DisplayName "Rastro dev" -Direction Inbound -Protocol TCP -LocalPort 5173,8000 -Action Allow -Profile Private
```

---

## 6. APK de desenvolvimento (sem Firebase)

É um APK que **abre o servidor da sua máquina** dentro do app. Serve para
testar no celular sem nenhuma conta na nuvem. Só funciona no seu Wi-Fi e com o
`docker compose up` rodando.

```powershell
cd frontend
```

```powershell
npm install
```

```powershell
npm run build
```

Troque o IP pelo do seu PC:

```powershell
$env:RASTRO_DEV_URL="http://192.168.0.10:5173"; npx cap sync android
```

```powershell
cd android
```

```powershell
.\gradlew.bat assembleDebug
```

O APK sai em `frontend\android\app\build\outputs\apk\debug\app-debug.apk`.

> **Importante:** depois, para voltar ao modo normal, rode `npx cap sync
> android` **sem** a variável `RASTRO_DEV_URL` (feche o terminal ou rode
> `Remove-Item Env:RASTRO_DEV_URL`). Senão o APK de produção também vai tentar
> abrir o seu PC.

---

## 7. Criar o projeto no Firebase

### 7.1 Projeto

1. Entre em https://console.firebase.google.com → **Adicionar projeto**.
2. Nome: `rastro` (o Firebase sugere um ID tipo `rastro-a1b2c`; anote, é o
   **ID do projeto**).
3. Ative o Google Analytics quando perguntar (é o que alimenta as métricas).
4. **Plano Blaze** (pago por uso): o Cloud Run e as reescritas do Hosting para
   o Cloud Run exigem. Com o volume de uma fazenda o custo fica perto de zero,
   mas **configure um alerta de orçamento** em *Faturamento › Orçamentos*.

### 7.2 Authentication (login)

1. *Criação › Authentication › Vamos começar*.
2. Aba **Método de login** → **E-mail/senha** → Ativar → Salvar.
3. Aba **Configurações › Política de senha**: exija **12 caracteres** (mesma
   régua do Rastro).
4. Aba **Configurações › Domínios autorizados**: confira que `localhost` e
   `SEU-PROJETO.web.app` estão na lista (o APK usa `localhost`).
5. (Opcional) *Templates* → traduza o e-mail de redefinição de senha para
   português.

### 7.3 App Web (para o site e o login dentro do APK)

1. *Configurações do projeto* (engrenagem) → **Seus apps** → ícone `</>`.
2. Apelido: `rastro-web`. **Marque** "Configurar o Firebase Hosting".
3. Ele mostra um `firebaseConfig = {...}`. Copie os valores para
   `frontend\.env.production.local`, usando o modelo:

```powershell
Copy-Item frontend\.env.firebase.example frontend\.env.production.local
```

```powershell
notepad frontend\.env.production.local
```

| No `firebaseConfig` | No `.env.production.local` |
|---|---|
| `apiKey` | `VITE_FIREBASE_API_KEY` |
| `authDomain` | `VITE_FIREBASE_AUTH_DOMAIN` |
| `projectId` | `VITE_FIREBASE_PROJECT_ID` |
| `storageBucket` | `VITE_FIREBASE_STORAGE_BUCKET` |
| `messagingSenderId` | `VITE_FIREBASE_MESSAGING_SENDER_ID` |
| `appId` | `VITE_FIREBASE_APP_ID` |
| `measurementId` | `VITE_FIREBASE_MEASUREMENT_ID` |

> Esses valores **não são segredo**: vão dentro do JavaScript de todo app
> Firebase. Mesmo assim o arquivo fica fora do git, para cada ambiente ter o
> seu.

### 7.4 App Android (push, Crashlytics, Analytics)

1. *Configurações do projeto › Seus apps* → ícone do **Android**.
2. **Nome do pacote: `com.madeiragab.rastro`** (tem que ser exatamente este;
   está em `frontend/capacitor.config.ts` e `frontend/android/app/build.gradle`).
3. Apelido: `Rastro Android`.
4. **SHA-1** (opcional, mas recomendado). Pegue o da sua chave de release:

```powershell
keytool -list -v -keystore frontend\android\rastro-release.jks -alias rastro
```

5. Baixe o **`google-services.json`** e coloque em:

```
frontend\android\app\google-services.json
```

6. Pule os passos de "adicionar SDK" do assistente — o projeto já está pronto.

Com esse arquivo no lugar, o build liga sozinho os plugins do Google Services
e do Crashlytics (`frontend/android/app/build.gradle`). Sem ele o APK compila
normalmente, só que **sem** push, Crashlytics e Analytics.

### 7.5 Crashlytics

*Executar › Crashlytics* → **Ativar o Crashlytics**. O painel só mostra dados
depois que o app abrir pela primeira vez **com** o `google-services.json`.

### 7.6 Cloud Messaging (push)

Nada a configurar no console: a API usa a **API HTTP v1 do FCM** com a conta de
serviço do Cloud Run. Só confirme que a **Firebase Cloud Messaging API (V1)**
aparece como ativada em *Configurações do projeto › Cloud Messaging*.

---

## 8. Publicar a API no Cloud Run

### 8.1 Banco Postgres com PostGIS

O Cloud Run não guarda dados; o banco fica fora. Opções:

| Opção | Custo | PostGIS |
|---|---|---|
| **Cloud SQL** (Google) | ~US$ 10/mês na menor máquina | sim (`CREATE EXTENSION postgis`) |
| **Neon** | tem plano grátis | sim |
| **Supabase** | tem plano grátis | sim |

Crie um banco chamado `rastro` e anote a URL de conexão. A API cria as tabelas
e liga o PostGIS sozinha na primeira subida (migrações Alembic).

> Se o provedor não deixar a API rodar `CREATE EXTENSION postgis`, rode você
> mesmo no console SQL do provedor: `CREATE EXTENSION IF NOT EXISTS postgis;`

### 8.2 Variáveis

```powershell
Copy-Item .env.cloudrun.example .env.cloudrun
```

```powershell
notepad .env.cloudrun
```

Preencha `FIREBASE_PROJETO_ID`, `DATABASE_URL`, `SECRET_KEY`, `CORS_ORIGINS`,
`APP_URL` e `ADMIN_EMAIL`. Para gerar o `SECRET_KEY`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

> **`https://localhost` em `CORS_ORIGINS` é obrigatório para o APK.** É a
> origem do app instalado.

### 8.3 Deploy

```powershell
gcloud auth login
```

```powershell
gcloud config set project SEU-PROJETO
```

```powershell
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

```powershell
gcloud run deploy rastro-api --source backend --region southamerica-east1 --port 8000 --env-vars-file .env.cloudrun --allow-unauthenticated --min-instances 1 --max-instances 1 --no-cpu-throttling --memory 1Gi
```

Por que essas opções:

| Opção | Motivo |
|---|---|
| `--region southamerica-east1` | São Paulo; tem que ser a mesma do `firebase.json` |
| `--port 8000` | a imagem escuta na 8000 (`backend/Dockerfile`) |
| `--allow-unauthenticated` | quem autentica é a API (token do Firebase), não o Google |
| `--min-instances 1` + `--no-cpu-throttling` | a API tem laços em segundo plano (alertas, push, limpeza); sem isso eles congelam entre requisições |
| `--max-instances 1` | esses laços não podem rodar em duas instâncias ao mesmo tempo (alerta duplicado) |
| `--memory 1Gi` | o Argon2id usa 64 MiB por login; 512 MiB fica apertado |

A conta de serviço padrão do Cloud Run já consegue validar tokens e mandar
FCM no próprio projeto. Se der `PERMISSION_DENIED` no log, veja os
[erros do Firebase](#erros-do-firebase).

### 8.4 Pegar a senha inicial

```powershell
gcloud run services logs read rastro-api --region southamerica-east1 --limit 200 | Select-String -Context 0,14 "ACESSO INICIAL"
```

A conta do dono é criada **na API e no Firebase Auth** ao mesmo tempo. Se você
definiu `ADMIN_SENHA` no `.env.cloudrun`, a senha é essa.

### 8.5 Cadastrar a equipe

Pelo próprio app: **Conta › Equipe › Adicionar**. No modo Firebase, a API cria
a conta lá também, e a senha inicial aparece uma vez na tela. A pessoa troca no
primeiro acesso.

---

## 9. Publicar o site no Firebase Hosting

```powershell
firebase login
```

```powershell
Copy-Item .firebaserc.example .firebaserc
```

Edite `.firebaserc` e troque `SEU-PROJETO` pelo ID do projeto. Depois:

```powershell
cd frontend
```

```powershell
npm run build
```

```powershell
cd ..
```

```powershell
firebase deploy --only hosting
```

O site fica em `https://SEU-PROJETO.web.app`. O `firebase.json` reescreve
`/api/**` e `/health/**` para o serviço `rastro-api` do Cloud Run — por isso o
site não precisa saber onde a API está.

> O `npm run build` lê o `frontend\.env.production.local`. Confira que ele
> existe **antes** do build, senão o site sai no modo de login local e mostra
> "Configuração incompatível".

---

## 10. APK de produção (com Firebase)

Checklist antes de começar:

- [ ] `frontend\.env.production.local` preenchido (seção 7.3)
- [ ] `VITE_API_URL=https://SEU-PROJETO.web.app/api` **descomentado** nele
- [ ] `frontend\android\app\google-services.json` no lugar (seção 7.4)
- [ ] API no ar com `AUTH_MODO=firebase` e `https://localhost` no CORS (seção 8)
- [ ] Nenhum `RASTRO_DEV_URL` no terminal (`echo $env:RASTRO_DEV_URL` vazio)

### 10.1 Chave de assinatura (só na primeira vez)

O Android só instala APK assinado, e **atualizações precisam da mesma chave**.
Se você já tem `frontend\android\rastro-release.jks` e
`frontend\android\keystore.properties`, pule.

```powershell
cd frontend\android
```

```powershell
keytool -genkeypair -v -keystore rastro-release.jks -alias rastro -keyalg RSA -keysize 4096 -validity 10000
```

Ele pede uma senha. Crie o `keystore.properties` ao lado:

```properties
storeFile=rastro-release.jks
storePassword=A_SENHA_QUE_VOCE_DIGITOU
keyAlias=rastro
keyPassword=A_SENHA_QUE_VOCE_DIGITOU
```

> ⚠️ **Faça backup desses dois arquivos** (pendrive, gerenciador de senhas).
> Eles ficam fora do git de propósito. **Se perder, não tem volta:** os
> celulares com o app instalado não aceitam atualização assinada por outra
> chave — cada pessoa teria que desinstalar e instalar de novo.

### 10.2 Gerar

```powershell
cd frontend
```

```powershell
npm install
```

```powershell
npm run build
```

```powershell
npx cap sync android
```

```powershell
cd android
```

```powershell
.\gradlew.bat assembleRelease
```

O APK assinado sai em:

```
frontend\android\app\build\outputs\apk\release\app-release.apk
```

Confira a assinatura (opcional):

```powershell
& "$env:ANDROID_HOME\build-tools\35.0.0\apksigner.bat" verify --print-certs app\build\outputs\apk\release\app-release.apk
```

### 10.3 Pela interface do Android Studio (alternativa)

```powershell
npx cap open android
```

Espere o *Gradle sync* terminar e use **Build › Generate Signed App Bundle or
APK › APK**. Para a Play Store, escolha **Android App Bundle** (`.aab`) e rode
`.\gradlew.bat bundleRelease`.

### 10.4 Trocar o ícone

O ícone (a vaquinha com o brinco rastreador) sai de `frontend\recursos\vaca.svg`.
Edite o SVG e regenere todos os tamanhos (Android, notificação, splash, PWA):

```powershell
cd frontend
```

```powershell
npm install -D sharp
```

```powershell
node scripts/gerar-icones.mjs
```

---

## 11. Instalar o APK no celular

### Pelo cabo (adb)

1. No celular: *Configurações › Sobre o telefone* → toque 7× em **Número da
   versão** (liga o modo desenvolvedor).
2. *Configurações › Sistema › Opções do desenvolvedor* → ligue **Depuração USB**.
3. Conecte o cabo e aceite o aviso no celular.

```powershell
& "$env:ANDROID_HOME\platform-tools\adb.exe" devices
```

```powershell
& "$env:ANDROID_HOME\platform-tools\adb.exe" install -r frontend\android\app\build\outputs\apk\release\app-release.apk
```

### Sem cabo

Mande o `.apk` pelo WhatsApp, Google Drive ou e-mail para o celular, toque
nele e permita **"Instalar apps desconhecidos"** para o app que abriu o
arquivo. O Play Protect pode avisar que o app "não é conhecido" — é normal
para APK fora da Play Store; toque em *Instalar mesmo assim*.

### Primeiro uso

1. Abra o Rastro → entre com o e-mail e a senha.
2. Aceite **Permitir notificações** (Android 13+ pergunta).
3. Em **Conta › Notificações** deve aparecer *ligado*.
4. Teste: no site, aba **Simular** → *Fugir do pasto*. Em ~25 s o alerta chega
   no celular, mesmo com o app fechado.

---

## 12. Lançar uma versão nova

1. Aumente a versão em `frontend\android\app\build.gradle`:
   ```gradle
   versionCode 2          // inteiro, SEMPRE maior que o anterior
   versionName "0.3.0"    // o que a pessoa vê
   ```
2. Gere de novo (seção 10.2) com a **mesma chave**.
3. Instale por cima (`adb install -r` ou abrindo o APK) — os dados e o login
   continuam.

Mudou só a API? `gcloud run deploy ...` de novo (seção 8.3). Mudou só o site?
`npm run build` + `firebase deploy --only hosting`. O APK só precisa ser
regerado quando muda algo em `frontend/`.

---

## 13. Erros comuns

### Erros do Docker / máquina

| Sintoma | Causa | Solução |
|---|---|---|
| `docker: command not found` / `'docker' não é reconhecido` | Docker Desktop não instalado ou não iniciado | instale (seção 2) e **abra o Docker Desktop** antes |
| `no virtualization available` / `WSL 2 installation is incomplete` | falta o WSL2 ou virtualização desligada na BIOS | `wsl --install` como administrador e reinicie; se persistir, ligue *Intel VT-x / AMD-V* na BIOS |
| `port is already allocated` (5432, 8000 ou 5173) | outro programa usando a porta (ex.: um Postgres instalado) | feche o programa ou pare o serviço: `Stop-Service postgresql*` |
| Login diz "e-mail ou senha incorretos" na primeira vez | senha errada do bloco `ACESSO INICIAL` (ela muda a cada banco novo) | rode o comando da seção 3.2 de novo; se perdeu, `docker compose down -v` |
| `banco de dados nao respondeu a tempo` | Postgres ainda subindo ou `DATABASE_URL` errada | espere e rode `docker compose up` de novo; confira a URL |
| Mapa cinza, sem ruas | sem internet (os mapas vêm do OpenStreetMap) | confira a conexão |
| Celular não abre `http://IP:5173` | firewall do Windows ou redes diferentes | seção 5; confira que o celular não está no 4G |

### Erros da API (produção)

| Sintoma no log | Solução |
|---|---|
| `SECRET_KEY ausente ou fraca` | gere uma com 48 bytes (seção 8.2) |
| `COOKIE_SECURE precisa ser true em producao` | `COOKIE_SECURE: "true"` |
| `SIMULATOR_ENABLED precisa ser false em producao` | `SIMULATOR_ENABLED: "false"` (para demo, use `AMBIENTE: "desenvolvimento"` — mas aí a API fica sem as travas de produção) |
| `SMTP_HOST ausente` | só acontece no modo `local`. No modo `firebase` o e-mail é do Firebase |
| `AUTH_MODO=firebase exige FIREBASE_PROJETO_ID` | preencha o ID do projeto |
| `CORS_ORIGINS contem origem http:// nao-local` | use só `https://` em produção |
| `type "geometry" does not exist` | PostGIS não está ligado no banco: `CREATE EXTENSION postgis;` |
| `Container failed to start and listen on the port` | faltou `--port 8000` no `gcloud run deploy` |
| Alertas não disparam / push não sai | Cloud Run sem `--min-instances 1 --no-cpu-throttling` |

### Erros do Firebase

| Sintoma | Causa | Solução |
|---|---|---|
| Tela de login: **"Configuração incompatível"** | app e API em modos diferentes | build com `VITE_FIREBASE_*` ⇔ `AUTH_MODO=firebase` |
| Tela de login: **"Servidor fora do ar ou endereço da API errado"** | `VITE_API_URL` errada no APK, API fora do ar, ou CORS sem `https://localhost` | abra `https://SEU-PROJETO.web.app/health` no navegador do celular; confira o CORS |
| "conta sem acesso a nenhuma fazenda" | a conta existe no Firebase mas não no Rastro | o dono cadastra o e-mail em **Conta › Equipe** |
| Entrei com conta criada no console do Firebase e deu 401 | o e-mail não está verificado | crie a conta pelo app (**Equipe**), não pelo console; ou marque o e-mail como verificado |
| `auth/operation-not-allowed` | login por e-mail/senha desligado | seção 7.2 |
| `auth/unauthorized-domain` | domínio fora da lista | *Authentication › Configurações › Domínios autorizados* |
| `auth/password-does-not-meet-requirements` | senha fora da política do projeto | use 12+ caracteres |
| `PERMISSION_DENIED` ao criar usuário ou mandar push (log da API) | conta de serviço do Cloud Run sem papel | no IAM, dê à conta `...-compute@developer.gserviceaccount.com` os papéis **Firebase Authentication Admin** e **Firebase Cloud Messaging Admin** |
| `Your default credentials were not found` (API fora do Cloud Run) | sem credencial do Google | baixe uma chave de conta de serviço (*Configurações › Contas de serviço › Gerar nova chave*) e aponte `FIREBASE_CREDENCIAIS` para o JSON — **nunca versione esse arquivo** |
| Site no Hosting dá 404 em `/api/...` | serviço/região diferentes do `firebase.json` | o Cloud Run tem que se chamar `rastro-api` em `southamerica-east1` (ou ajuste o `firebase.json`) |

### Erros do Android / Gradle

| Sintoma | Causa | Solução |
|---|---|---|
| `SDK location not found` | o Gradle não acha o SDK | crie `frontend\android\local.properties` com `sdk.dir=C:/Users/SEU_USUARIO/AppData/Local/Android/Sdk` |
| `Unsupported class file major version 65` ou `requires Java 17` | JDK errado (21 ou 11) | instale o JDK **17** e aponte o `JAVA_HOME` para ele |
| `Failed to install the following Android SDK packages ... licences have not been accepted` | licenças do SDK | `& "$env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat" --licenses` e aceite tudo |
| `Filename too long` / `unable to open for write` / `The system cannot find the path specified` | caminho > 260 caracteres no Windows | mova o projeto para `C:\dev\rastro` **ou** ative caminhos longos (como administrador): `New-ItemProperty -Path HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force` |
| `File google-services.json is missing` | aplicaram o plugin à mão | não aplique; o `build.gradle` já só liga quando o arquivo existe |
| `No matching client found for package name` | `google-services.json` de outro pacote | o app Android no Firebase precisa ser `com.madeiragab.rastro` |
| `Could not resolve com.google.firebase:...` / timeout | sem internet ou proxy | o primeiro build baixa ~500 MB; tente de novo com internet estável |
| `Keystore was tampered with, or password was incorrect` | senha do `keystore.properties` errada | corrija a senha; se perdeu de vez, veja a seção 10.1 |
| Build fica parado em `Daemon will be stopped` / memória | pouca RAM | feche o Android Studio e rode `.\gradlew.bat --stop` antes |
| Mudei o código e o APK continua velho | esqueceu do build web ou do sync | sempre `npm run build` **e** `npx cap sync android` antes do Gradle |

### Erros na instalação do APK

| Sintoma | Causa | Solução |
|---|---|---|
| "App não instalado" / `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | já existe um Rastro assinado com **outra chave** (ex.: debug × release) | desinstale o antigo e instale de novo |
| `INSTALL_FAILED_VERSION_DOWNGRADE` | `versionCode` menor que o instalado | aumente o `versionCode` (seção 12) |
| "Instalação bloqueada" | fontes desconhecidas desligadas | permita "Instalar apps desconhecidos" para o app que abriu o APK |
| `adb: no devices/emulators found` | depuração USB desligada ou cabo só de carga | seção 11; troque o cabo; aceite o aviso "Permitir depuração" |
| App abre em **tela branca** | erro de JavaScript ou build web não copiado | `npx cap sync android` e gere de novo; para ver o erro, com o celular no cabo abra `chrome://inspect` no PC |

### Erros de push no celular

| Sintoma | Causa | Solução |
|---|---|---|
| Notificações: "Push indisponível neste build" | APK gerado **sem** `google-services.json` | seção 7.4 e gere de novo |
| Notificações "desligado" e o botão não liga | permissão negada | *Configurações › Apps › Rastro › Notificações* → permitir |
| Push só chega com o app aberto | economia de bateria agressiva (Xiaomi, Samsung, Motorola) | *Configurações › Apps › Rastro › Bateria* → **Sem restrições**; na Xiaomi também *Início automático* |
| Push não chega nunca | API sem Firebase ou token não registrado | log da API deve mostrar `Firebase Admin inicializado`; saia e entre no app para registrar de novo |

---

## 14. Cola de comandos

```powershell
docker compose up --build
```

```powershell
docker compose logs api | Select-String -Context 0,12 "ACESSO INICIAL"
```

```powershell
docker compose down -v
```

```powershell
cd frontend; npm run build; npx cap sync android; cd android; .\gradlew.bat assembleRelease
```

```powershell
& "$env:ANDROID_HOME\platform-tools\adb.exe" install -r frontend\android\app\build\outputs\apk\release\app-release.apk
```

```powershell
gcloud run deploy rastro-api --source backend --region southamerica-east1 --port 8000 --env-vars-file .env.cloudrun --allow-unauthenticated --min-instances 1 --max-instances 1 --no-cpu-throttling --memory 1Gi
```

```powershell
cd frontend; npm run build; cd ..; firebase deploy --only hosting
```

### Onde fica cada configuração

| Arquivo | O que tem | Vai pro git? |
|---|---|---|
| `frontend/.env.production.local` | config Web do Firebase, `VITE_API_URL` | ❌ |
| `frontend/android/app/google-services.json` | config Android do Firebase | ❌ |
| `frontend/android/keystore.properties` + `rastro-release.jks` | chave de assinatura | ❌ **faça backup** |
| `frontend/android/local.properties` | caminho do SDK | ❌ |
| `.env.cloudrun` | segredos da API | ❌ |
| `.firebaserc` | ID do projeto Firebase | ❌ |
| `firebase.json` | Hosting e reescritas para o Cloud Run | ✅ |
| `frontend/capacitor.config.ts` | nome do pacote, modo dev | ✅ |
| `frontend/recursos/vaca.svg` | o ícone | ✅ |
