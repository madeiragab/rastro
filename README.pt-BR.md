# Rastro

[🇬🇧 English](README.md) · **🇧🇷 Português**

Rastreamento em tempo real e geocerca para rebanho bovino.

O produtor desenha o pasto no mapa e recebe alerta quando o animal **sai da área**,
**fica parado tempo demais** ou **perde comunicação**.

App web mobile-first com simulador de rebanho embutido — roda sem hardware nenhum.

> **Status: MVP / demonstração.** Não está pronto para produção. Ver
> [Pendências antes de produção](#pendências-antes-de-produção).

---

## Subir

```bash
docker compose up --build
```

| Serviço | URL |
|---|---|
| App | http://localhost:5173 |
| API (Swagger) | http://localhost:8000/docs |
| Banco | localhost:5432 |

O primeiro start cria o schema, habilita o PostGIS e carrega os dados de
demonstração: uma fazenda em Uberaba/MG, dois pastos e 14 animais. O simulador
começa a gerar telemetria em seguida.

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

Para desenhar um pasto novo: toque no botão **⬡**, toque nos vértices no mapa, dê um
nome e salve.

---

## Interface

Mobile-first: o mapa ocupa a tela inteira e tudo mais flutua sobre ele.

- **Folha inferior** com três paradas — arraste, ou toque na alça. Recolhida, ainda
  mostra uma faixa compacta de contadores.
- **Abas**: Rebanho, Alertas (com selo de quantidade) e Simular.
- Tocar num animal leva o mapa até ele — mas o mapa nunca se move sozinho quando
  chega posição nova. Mapa que pula a cada leitura é insuportável no celular.
- A partir de 900 px de largura a folha vira painel lateral fixo, então o mesmo
  código serve no desktop.

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
├── backend/
│   └── app/
│       ├── main.py            # bootstrap, CORS, ciclo de vida, simulador
│       ├── config.py          # TODOS os limiares de alerta ficam aqui
│       ├── database.py        # engine, sessão, criação do schema
│       ├── models.py          # Fazenda, Pasto, Animal, Posicao, Alerta
│       ├── schemas.py         # contratos de entrada e saída
│       ├── seed.py            # carga de demonstração
│       ├── api/
│       │   ├── serializers.py # ORM -> schema (extrai lat/lon da geometria)
│       │   └── routes/        # um módulo por recurso
│       └── services/
│           ├── geofence.py    # ponto-em-polígono e distância (PostGIS)
│           ├── alertas.py     # as três regras de alerta
│           ├── telemetria.py  # ingestão de posição (ponto único)
│           └── simulador.py   # rebanho virtual
└── frontend/
    └── src/
        ├── App.tsx            # estado e polling
        ├── api.ts             # cliente HTTP  ← reaproveitável no React Native
        ├── types.ts           # espelho dos schemas  ← reaproveitável
        └── components/
            ├── MapaView.tsx
            ├── FolhaInferior.tsx   # folha deslizante, escrita à mão
            ├── TirasResumo.tsx
            ├── ListaAnimais.tsx
            ├── FeedAlertas.tsx
            └── PainelSimulacao.tsx
```

### Por que PostGIS

O ponto-em-polígono roda no banco (`ST_Contains`), não em Python. O banco já tem
índice espacial, e a distância em metros sai correta convertendo para `geography` —
sem erro de projeção. Com o rebanho crescendo, é essa decisão que evita reescrever a
camada de dados depois.

`api.ts` e `types.ts` são independentes de framework de propósito: o app React Native
planejado reaproveita os dois como estão.

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

| Método | Rota | Para quê |
|---|---|---|
| `GET` | `/api/fazenda` | Fazenda atual (o MVP é monofazenda) |
| `GET` | `/api/resumo` | Contadores do painel |
| `GET` | `/api/pastos` | Lista de pastos com área e nº de animais |
| `POST` | `/api/pastos` | Cria pasto a partir dos vértices desenhados |
| `DELETE` | `/api/pastos/{id}` | Remove pasto (recusa se houver animais vinculados) |
| `GET` | `/api/animais` | Animais com última posição e status |
| `GET` | `/api/animais/{id}` | Um animal |
| `GET` | `/api/animais/{id}/trilha` | Trilha de posições recentes |
| `GET` | `/api/alertas` | Alertas, abertos por padrão |
| `POST` | `/api/alertas/{id}/resolver` | Resolve um alerta |
| `POST` | `/api/alertas/animal/{id}/resolver` | Resolve todos os alertas de um animal |
| `POST` | `/api/telemetria` | **Ingestão de posição — a porta de entrada do hardware** |
| `POST` | `/api/simulacao/cenario` | Força um cenário (só demonstração) |
| `POST` | `/api/simulacao/reiniciar` | Reinicia a simulação (só demonstração) |

Referência interativa completa em http://localhost:8000/docs.

---

## Integrar hardware real

O simulador e o gateway real entram pelo mesmo caminho. Basta o gateway chamar:

```bash
curl -X POST http://localhost:8000/api/telemetria \
  -H "Content-Type: application/json" \
  -d '{"brinco":"076000000000001","lat":-19.7480,"lon":-47.9320,"atividade":0.6,"bateria_pct":88}'
```

Nenhuma regra de negócio muda. Desligue o simulador com `SIMULATOR_ENABLED=false`.

Os brincos usam numeração de 15 dígitos com prefixo `076` (código do Brasil),
alinhada ao **PNIB** — o Plano Nacional de Identificação Individual de Bovinos e
Búfalos, que torna a identificação individual obrigatória para movimentação de
bovinos a partir de 2033.

---

## Pendências antes de produção

- **Autenticação.** A API está totalmente aberta, inclusive o endpoint de telemetria,
  que aceita posição de qualquer origem. Precisa de chave por gateway ou mTLS, e login
  no painel. É bloqueante para qualquer coisa além de demonstração local.
- **Migrações.** O schema é criado por `create_all`. Trocar por Alembic quando
  estabilizar.
- **Tempo real.** O cliente faz polling a cada 3 s. Trocar por WebSocket ou SSE quando
  o volume justificar.
- **Notificação push.** Hoje o alerta só aparece dentro do painel. O push para o
  celular é a promessa central do produto e ainda não existe — é também o principal
  motivo do app React Native estar no roadmap.
- **Multi-fazenda.** O MVP assume uma fazenda só (`GET /api/fazenda` devolve a
  primeira).

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
PostgreSQL 16 · PostGIS 3.4 · Docker Compose
