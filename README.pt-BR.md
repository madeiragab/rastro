# Rastro

[🇬🇧 English](README.md) · **🇧🇷 Português**

[![ci](https://github.com/madeiragab/rastro/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/madeiragab/rastro/actions/workflows/ci.yml)

Rastreamento em tempo real e geocerca para rebanho bovino.

O produtor desenha o pasto no mapa e recebe alerta quando o animal **sai da área**,
**fica parado tempo demais** ou **perde comunicação**.

App web mobile-first com simulador de rebanho embutido — roda sem hardware nenhum.

> **Status: MVP / demonstração.** Roda de ponta a ponta e está verificado: 124
> testes contra PostGIS real — [rodados pelo CI a cada push](https://github.com/madeiragab/rastro/actions/workflows/ci.yml),
> contra um serviço `postgis/postgis:16-3.4` de verdade, não contra dublê — mais
> uma passagem manual por login, rotação de sessão, telemetria autenticada e o
> ciclo completo de alerta de geocerca. **Não**
> passou por auditoria externa nem por teste de intrusão, e vários requisitos de
> produção continuam faltando — ver
> [Pendências antes de produção](#pendências-antes-de-produção).

📚 **[Documentação completa](docs/README.pt-BR.md)** — [requisitos](docs/requisitos.md) ·
[arquitetura](docs/arquitetura.md) · [segurança](docs/seguranca.md) ·
[decisões](docs/decisoes.md) · [implantação](docs/implantacao.md) ·
[hardware](docs/arquitetura-hardware.md) ·
[protocolo](docs/protocolo-dispositivos.md)

---

## Subir

```bash
docker compose up --build
```

| Serviço | URL |
|---|---|
| App | http://localhost:5173 |
| API (Swagger) | http://localhost:8000/docs |
| Banco | 127.0.0.1:5432 |

O primeiro start cria o schema, habilita o PostGIS e carrega os dados de
demonstração: uma fazenda em Uberaba/MG, dois pastos e 14 animais. O simulador
começa a gerar telemetria em seguida.

**As credenciais iniciais aparecem no log da API, uma única vez.** Procure o bloco
`ACESSO INICIAL` em `docker compose logs api`. Ele traz o e-mail de acesso, uma
senha sorteada e uma chave de gateway. Nada é fixo no código — credencial default
versionada é como a maior parte dos sistemas expostos cai.

Zerar tudo:

```bash
docker compose down -v
```

> **Nota para Windows.** O Docker Desktop precisa do backend WSL2. Se o `docker info`
> reportar `no virtualization available`, o WSL não está instalado — rode
> `wsl --install` num PowerShell como Administrador, reinicie a máquina e abra o
> Docker Desktop de novo.

### Abrir no celular

O app é mobile-first. Para abrir num aparelho de verdade na mesma rede Wi-Fi,
descubra o IP da máquina e acesse `http://<seu-ip>:5173`. No Android/Chrome dá para
"Adicionar à tela inicial" — o manifest está incluído, então abre em tela cheia.

---

## Como demonstrar

A aba **Simular** força um cenário no animal selecionado. Escolha um animal na lista
ou toque nele no mapa, e então:

| Botão | O que acontece |
|---|---|
| **Fugir do pasto** | O animal caminha em linha reta para fora da divisa. Após 2 leituras consecutivas além da zona de tolerância, dispara o alerta de área (~25 s). |
| **Ficar parado** | A atividade do acelerômetro cai a zero. Após 90 s, dispara o alerta de imobilidade. |
| **Perder sinal** | O brinco para de reportar. Após 60 s de silêncio, dispara o alerta de perda de sinal. |
| **Pastando** | Volta ao normal; os alertas abertos se resolvem sozinhos. |

Para desenhar um pasto novo: toque em **⬡**, toque nos vértices no mapa, dê um nome
e salve.

---

## Interface

Mobile-first: o mapa ocupa a tela inteira e tudo mais flutua sobre ele.

- **Folha inferior** com três paradas — arraste, ou toque na alça. Recolhida, ainda
  mostra uma faixa compacta de contadores.
- **Abas**: Rebanho, Alertas (com selo), Simular e Conta.
- Tocar num animal leva o mapa até ele — mas o mapa nunca se move sozinho quando
  chega posição nova. Mapa que pula a cada leitura é insuportável no celular.
- A partir de 900 px de largura a folha vira painel lateral fixo, então o mesmo
  código serve no desktop.

---

## Segurança

Texto completo em [docs/seguranca.md](docs/seguranca.md), com a lista honesta do
que **não** está coberto.

| Frente | Abordagem |
|---|---|
| Senha | Argon2id (64 MiB, t=3), normalizada em NFKC, reidratação automática quando o custo muda. Política do NIST SP 800-63B: comprimento + lista de bloqueio, sem regras de composição |
| Sessão | Access JWT de 15 min guardado **só em memória** + refresh opaco de 14 dias em cookie `HttpOnly`, `SameSite=strict` |
| Roubo de token | Rotação do refresh com detecção de reuso — token repetido revoga a família inteira da sessão (OAuth 2.0 Security BCP) |
| CSRF | `SameSite=strict` mais double-submit comparado em tempo constante |
| Força bruta | Bloqueio em banco, por conta **e** por IP (este último pega o password spraying) |
| Enumeração | Mensagem genérica, tempo constante para e-mail inexistente, e bloqueio que vale para ele também |
| Dispositivos | Chave de API por gateway, com hash Argon2id, exibida uma vez, revogável e restrita à própria fazenda |
| Cabeçalhos | CSP fechada, `nosniff`, `DENY` de frame, `no-referrer`, COOP/CORP, `no-store`, HSTS sob HTTPS |
| Configuração | A aplicação **se recusa a subir** em produção com segredo fraco, cookie inseguro, CORS `http://` não-local ou simulador ligado |
| Autorização | Declarada no roteador, então rota nova nasce protegida; três papéis verificados no servidor |
| Equipe | Senha inicial sorteada pelo servidor e exibida uma vez; rebaixar ou desativar invalida o token na hora; ninguém altera a própria conta |
| Recuperação de senha | Token opaco de uso único, 30 min, 3 pedidos por hora; redefinir revoga sessões e demais links pendentes |

---

## Arquitetura

```
navegador do celular (React + Leaflet)
      │  HTTP /api  (proxy do Vite)
FastAPI
      │
PostgreSQL + PostGIS
```

```
rastro/
├── docker-compose.yml
├── docs/                       # requisitos, arquitetura, segurança, ADRs (PT + EN)
├── backend/
│   └── app/
│       ├── main.py             # bootstrap, CORS, cabeçalhos, ciclo de vida
│       ├── config.py           # TODOS os limiares e parâmetros de segurança
│       ├── database.py         # engine, sessão, criação do schema
│       ├── models.py           # domínio + usuários, sessões, chaves, auditoria
│       ├── schemas.py          # contratos e faixas de entrada
│       ├── middleware.py       # cabeçalhos de segurança na resposta
│       ├── seed.py             # dados de demonstração + credenciais iniciais
│       ├── security/
│       │   ├── senhas.py       # Argon2id + política de senha
│       │   ├── tokens.py       # access JWT, refresh, CSRF
│       │   ├── chaves.py       # chaves de API dos gateways
│       │   ├── limites.py      # bloqueio contra força bruta
│       │   └── auditoria.py    # trilha de auditoria
│       ├── api/
│       │   ├── deps.py         # dependências de autenticação e autorização
│       │   ├── serializers.py  # ORM -> schema (extrai lat/lon da geometria)
│       │   └── routes/         # um módulo por recurso
│       └── services/
│           ├── geofence.py     # ponto-em-polígono e distância (PostGIS)
│           ├── alertas.py      # as três regras de alerta
│           ├── telemetria.py   # ingestão de posição (ponto único)
│           ├── simulador.py    # rebanho virtual
│           └── manutencao.py   # limpeza periódica
└── frontend/
    └── src/
        ├── App.tsx             # estado, polling, portão de sessão
        ├── api.ts              # cliente HTTP  ← reaproveitável no React Native
        ├── types.ts            # espelho dos schemas  ← reaproveitável
        └── components/
```

### Por que PostGIS

O ponto-em-polígono roda no banco (`ST_Contains`), não em Python. O banco já tem
índice espacial, e a distância em metros sai correta convertendo para `geography` —
sem erro de projeção. Com o rebanho crescendo, é essa decisão que evita reescrever a
camada de dados depois.

---

## As três regras de alerta

Cada uma carrega a mitigação de alarme falso. Um produtor que recebe alerta falso
desinstala o aplicativo — esse é o principal risco de adoção do produto, não a
tecnologia.

**1. Fora da área.** Zona de tolerância de 25 m ao redor do polígono, mais exigência
de 2 leituras consecutivas fora. Sem isso, o erro do GNSS gera alarme contínuo com o
animal pastando junto à cerca.

**2. Sem movimento.** Decidido pelo acelerômetro, não pelo GNSS parado. GNSS sozinho
mente: bovino deitado ruminando fica estático por horas em condição perfeitamente
normal. É o alerta de maior valor comercial — detecta morte, parto travado,
atolamento e fratura.

**3. Perda de sinal.** Limiar relativo à periodicidade do próprio dispositivo, não um
valor fixo global, porque a periodicidade varia por animal e por terreno. Cobre três
causas distintas: brinco arrancado (furto), bateria esgotada e área sem propagação.

Todos os limiares ficam em [`backend/app/config.py`](backend/app/config.py),
**comprimidos para demonstração**. Os valores reais de campo estão documentados ao
lado de cada um (imobilidade 4 h, reporte a cada 30 min).

---

## API

Tudo sob `/api` exige autenticação. `/health` e o fluxo de login são os únicos
endpoints públicos.

| Método | Rota | Autenticação | Para quê |
|---|---|---|---|
| `POST` | `/api/auth/login` | — | Entrar; grava os cookies de refresh e CSRF |
| `POST` | `/api/auth/refresh` | cookie + CSRF | Rotaciona a sessão e devolve access novo |
| `POST` | `/api/auth/logout` | cookie | Revoga a família da sessão |
| `GET` | `/api/auth/eu` | usuário | Usuário atual |
| `POST` | `/api/auth/senha` | usuário | Troca a senha (encerra todas as sessões) |
| `POST` | `/api/auth/esqueci` | — | Pede link de redefinição (responde igual exista ou não a conta) |
| `POST` | `/api/auth/redefinir` | token | Consome o link e grava a senha nova |
| `GET` `POST` `PATCH` | `/api/usuarios` | dono | Gerencia a equipe e os papéis |
| `GET` | `/api/push/chave-publica` | usuário | Chave VAPID para o navegador assinar |
| `POST` `DELETE` | `/api/push/inscricoes` | usuário | Registra ou cancela o aparelho |
| `GET` | `/api/fazenda` | usuário | Fazenda atual |
| `GET` | `/api/resumo` | usuário | Contadores do painel |
| `GET` | `/api/animais` | usuário | Animais com última posição e status |
| `GET` | `/api/animais/{id}/trilha` | usuário | Trilha de posições recentes |
| `GET` | `/api/alertas` | usuário | Alertas, abertos por padrão |
| `POST` | `/api/alertas/{id}/resolver` | usuário | Resolve um alerta |
| `GET` `POST` `DELETE` | `/api/pastos` | operador | Gerencia pastos |
| `GET` `POST` `DELETE` | `/api/gateways` | dono | Gerencia chaves de gateway |
| `POST` | `/api/telemetria` | **chave de gateway** | Ingestão de posição — porta de entrada do hardware |
| `POST` | `/api/simulacao/*` | operador | Força cenários (só demonstração) |

Referência interativa em http://localhost:8000/docs — desligada em produção.

---

## Integrar hardware real

O simulador e o gateway real usam o mesmo serviço. O gateway se autentica com a
própria chave:

```bash
curl -X POST http://localhost:8000/api/telemetria \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rastro_gw_<prefixo>_<segredo>" \
  -d '{"brinco":"076000000000001","lat":-19.7480,"lon":-47.9320,"atividade":0.6,"bateria_pct":88}'
```

Nenhuma regra de negócio muda. Desligue o simulador com `SIMULATOR_ENABLED=false`.

Os brincos usam numeração de 15 dígitos com prefixo `076` (código do Brasil),
alinhada ao **PNIB** — o Plano Nacional de Identificação Individual de Bovinos e
Búfalos, que torna a identificação individual obrigatória para movimentação de
bovinos a partir de 2033.

---

## Notificação push

O alerta chega ao celular **com o app fechado** — é a promessa central do
produto. Ative em **Conta → Notificações**.

Web Push com VAPID. O par de chaves é gerado na primeira necessidade e guardado
no banco, não em variável de ambiente: trocar a chave invalidaria todas as
inscrições, e os aparelhos só perceberiam deixando de receber aviso — falha
silenciosa, que é o pior tipo num sistema de alerta.

O envio roda num laço de fundo, não no caminho da requisição de telemetria: push
sai por HTTP para o serviço do fabricante do navegador, e o gateway não pode
esperar isso para confirmar uma posição. A marca `notificado_em` fica no próprio
alerta, então reiniciar no meio não perde nem duplica aviso.

**Restrição do navegador:** Service Worker só registra em contexto seguro —
HTTPS **ou** `localhost`. No celular, pela rede local, `http://192.168.x.x` não
serve. Daí o perfil de TLS abaixo.

## HTTPS local

```bash
TLS_HOST=192.168.0.12 docker compose --profile tls up
```

Sobe um Caddy em `https://localhost` (e no IP informado) com certificado emitido
por uma autoridade local. O navegador avisa até que essa autoridade seja
confiada no aparelho. Não sobe por padrão, e não redireciona HTTP — o acesso por
`localhost` continua funcionando como antes.

Em produção, troque por um domínio real: o Caddy resolve o Let's Encrypt
sozinho. Ligue `COOKIE_SECURE=true` junto.

## Pendências antes de produção

- **Segundo fator.** Não implementado. TOTP ao menos para o papel `dono`.
- **SMTP.** A recuperação de senha funciona, mas o link é escrito no log da API
  em vez de enviado por e-mail. Falta plugar um provedor em
  `services/notificacao.py` — a abstração já está isolada ali.
- **Multi-fazenda.** O MVP assume uma fazenda só.
- **Gestão de segredos.** Os segredos vêm de variável de ambiente, visível em
  `docker inspect`. Migrar para um cofre.
- **Limite de taxa geral.** Só login e recuperação de senha são limitados; o
  resto da API não.
- **Push no iOS.** Funciona pleno no Android/Chrome. No Safari exige o app
  adicionado à tela inicial — é o principal argumento a favor do React Native
  no roadmap.

A lista completa, com risco e remédio de cada item, está em
[docs/seguranca.md](docs/seguranca.md#o-que-não-está-protegido).

---

## Contexto

A escolha da stack saiu de um estudo de viabilidade sobre rastreamento bovino para o
pequeno produtor de Minas Gerais. Três achados guiaram o desenho:

1. **Implante com GPS não é viável** — por física, não por custo. Tecido atenua RF, a
   antena não cabe, e a energia de um enlace de satélite não pode ser armazenada com
   segurança sob a pele. O brinco auricular ganha em todos os eixos.
2. **LoRa não depende de operadora.** Roda na faixa ISM livre de 915 MHz com gateway
   do próprio produtor. "Não tem cobertura de LoRa" significa "não tem gateway
   instalado".
3. **Satélite direto funciona hoje, mas é caro** (~R$ 1.600/cabeça). Fica competitivo
   com NB-IoT NTN por volta de 2027.

O princípio de projeto que decorre disso: **concentrar o enlace de rádio caro em
poucos pontos — gateway ou coleira — em vez de replicá-lo em cada animal.**

---

## Testes

```bash
docker compose up -d db
cd backend
pip install -r requirements-dev.txt
pytest
```

**124 passando, 4 pulados** (os pulados são as rotas propositalmente públicas na
varredura de autorização). A execução leva cerca de 5 minutos.

A suíte roda contra **PostGIS de verdade**, num banco `rastro_test` separado que
ela mesma cria na primeira execução. A regra de geocerca *é* o `ST_Contains` mais
distância em `geography` — testar isso com um dublê seria testar o dublê.

O custo do Argon2 é reduzido por variável de ambiente dentro do `conftest.py`. Em
produção o custo *é* a proteção; no teste era só relógio.

O que cobre:

| Arquivo | Foco |
|---|---|
| `test_seguranca_primitivas.py` | Argon2id, política de senha, normalização NFKC, claims do JWT, recusa de `alg=none`, token adulterado e expirado, formato da chave de gateway |
| `test_auth.py` | Login, mensagem genérica para e-mail inexistente, bloqueio, rotação de refresh, **detecção de reuso revogando a família**, logout, troca de senha invalidando token antigo |
| `test_autorizacao.py` | Varredura parametrizada garantindo que **toda** rota da OpenAPI recusa acesso anônimo, mais a matriz de papéis e os cabeçalhos de segurança |
| `test_telemetria.py` | Autenticação por chave, recusa entre fazendas, faixas de entrada, carimbo no futuro ou antigo demais |
| `test_alertas.py` | As três regras — incluindo os casos que **não** podem disparar: uma leitura isolada fora, animal pastando dentro da tolerância, e GNSS parado com acelerômetro normal |

A varredura do `test_autorizacao.py` é a mais importante: ela falha se alguém
adicionar rota sem proteção, o que transforma o ADR-007 de intenção em regra
verificável.

---

## Desenvolver sem Docker

```bash
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
```

```bash
cd frontend && npm install && npm run dev
```

Precisa de um PostgreSQL com PostGIS. Ajuste `DATABASE_URL`.

---

## Stack

React 18 · TypeScript · Vite · Leaflet · FastAPI · SQLAlchemy 2.0 · GeoAlchemy2 ·
Argon2id · PyJWT · PostgreSQL 16 · PostGIS 3.4 · Docker Compose
