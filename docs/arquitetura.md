> 🇧🇷 **Português** · [🇬🇧 English](architecture.md)

# Arquitetura

Documento técnico do Rastro: como as partes se encaixam, por que estão assim e
onde estão os limites.

- [Visão geral](#visão-geral)
- [Containers](#containers)
- [Modelo de dados](#modelo-de-dados)
- [Fluxo de telemetria](#fluxo-de-telemetria)
- [Ciclo de vida do alerta](#ciclo-de-vida-do-alerta)
- [Autenticação](#autenticação)
- [Camadas do backend](#camadas-do-backend)
- [Frontend](#frontend)
- [Limites conhecidos](#limites-conhecidos)

---

## Visão geral

```mermaid
flowchart TB
    produtor(["👤 Produtor rural<br/>celular no bolso"])
    gateway(["📡 Gateway da fazenda<br/>agrega os brincos"])
    brinco(["🏷️ Brinco solar<br/>GNSS + acelerômetro"])

    subgraph rastro["Rastro"]
        app["App mobile-first<br/>React + Leaflet"]
        api["API<br/>FastAPI"]
        banco[("PostgreSQL<br/>+ PostGIS")]
    end

    osm(["🗺️ OpenStreetMap<br/>tiles do mapa"])

    brinco -->|"rádio<br/>(LoRa / NB-IoT)"| gateway
    gateway -->|"POST /api/telemetria<br/>X-API-Key"| api
    produtor -->|HTTPS| app
    app -->|"JSON + Bearer"| api
    app -.->|tiles| osm
    api <--> banco

    classDef externo fill:#1e262b,stroke:#7b8794,color:#e6edf1
    classDef interno fill:#1f4d3a,stroke:#2e9e63,color:#e6edf1
    class produtor,gateway,brinco,osm externo
    class app,api,banco interno
```

O hardware ainda não existe. No MVP, o papel de brinco e gateway é feito por um
**simulador** que roda dentro da API e escreve pelo mesmo caminho que o gateway
real usaria.

## Containers

```mermaid
flowchart LR
    subgraph compose["docker compose"]
        direction TB
        web["<b>web</b><br/>Vite dev server<br/>porta 5173"]
        api["<b>api</b><br/>Uvicorn + FastAPI<br/>porta 8000"]
        db[("<b>db</b><br/>postgis/postgis:16-3.4<br/>porta 5432")]
    end

    navegador(["Navegador"]) -->|"/"| web
    navegador -->|"/api/*"| web
    web -->|proxy| api
    api -->|SQLAlchemy| db
```

O proxy do Vite faz o app e a API compartilharem a mesma origem no navegador.
Isso não é conveniência: é o que permite usar `SameSite=strict` no cookie de
sessão sem quebrar nada.

Portas `db` e `api` publicadas em `127.0.0.1`. Só a `web` fica em `0.0.0.0`,
para ser possível abrir o app no celular pela rede local.

## Modelo de dados

```mermaid
erDiagram
    FAZENDA ||--o{ PASTO : "tem"
    FAZENDA ||--o{ ANIMAL : "tem"
    FAZENDA ||--o{ USUARIO : "tem"
    FAZENDA ||--o{ CHAVE_GATEWAY : "tem"
    PASTO ||--o{ ANIMAL : "aloca"
    ANIMAL ||--o{ POSICAO : "reporta"
    ANIMAL ||--o{ ALERTA : "gera"
    USUARIO ||--o{ SESSAO_REFRESH : "abre"
    USUARIO ||--o{ EVENTO_AUDITORIA : "registra"

    FAZENDA {
        int id PK
        string nome
        string proprietario
        string municipio
        string uf
    }
    PASTO {
        int id PK
        int fazenda_id FK
        string nome
        geometry geom "POLYGON 4326"
        float buffer_m "zona de tolerância"
    }
    ANIMAL {
        int id PK
        int fazenda_id FK
        int pasto_id FK
        string brinco UK "15 dígitos, PNIB"
        string status
        geometry ultima_geom "POINT 4326"
        timestamp ultimo_contato
        int leituras_fora "histerese"
        timestamp imovel_desde
    }
    POSICAO {
        int id PK
        int animal_id FK
        geometry geom "POINT 4326"
        float atividade "0..1, acelerômetro"
        timestamp registrada_em
    }
    ALERTA {
        int id PK
        int animal_id FK
        string tipo
        string severidade
        timestamp criado_em
        timestamp resolvido_em
    }
    USUARIO {
        int id PK
        string email UK
        string senha_hash "Argon2id"
        string papel
        timestamp senha_alterada_em
        int token_versao "invalida access tokens antigos"
    }
    SESSAO_REFRESH {
        int id PK
        int usuario_id FK
        string familia "cadeia de rotação"
        string token_hash UK "SHA-256"
        timestamp usada_em
        timestamp revogada_em
    }
    CHAVE_GATEWAY {
        int id PK
        int fazenda_id FK
        string prefixo UK "público"
        string chave_hash "Argon2id"
    }
    EVENTO_AUDITORIA {
        int id PK
        int usuario_id FK
        string acao
        string ip
    }
```

Três decisões que valem explicação:

**`ultima_geom` no animal é denormalização deliberada.** O mapa pede a posição
de todo o rebanho a cada 3 s. Buscar o último ponto varrendo `posicoes` a cada
ciclo custaria caro; manter uma cópia da última leitura custa uma coluna.

**`leituras_fora` e `imovel_desde` são estado do motor de alertas, não do
animal.** Ficam aqui porque a alternativa — recalcular o histórico a cada
leitura — seria mais cara sem ser mais correta.

**`familia` na sessão** agrupa toda a cadeia de rotações de um mesmo login. É o
que permite revogar um roubo de token inteiro de uma vez.

## Fluxo de telemetria

```mermaid
sequenceDiagram
    autonumber
    participant G as Gateway
    participant A as API
    participant S as Serviço de alertas
    participant D as PostGIS

    G->>A: POST /api/telemetria<br/>X-API-Key + posição
    A->>D: busca a chave pelo prefixo
    A->>A: Argon2.verify(segredo)
    Note over A: chave inválida → 401<br/>(tempo constante)

    A->>D: busca o animal pelo brinco
    Note over A: animal de outra fazenda → 404<br/>(não confirma existência)

    A->>D: INSERT posicao
    A->>D: UPDATE animal (ultima_geom, ultimo_contato)

    A->>S: avaliar_posicao()
    S->>D: ST_Contains(pasto, ponto)
    S->>D: ST_Distance(pasto::geography, ponto::geography)

    alt fora e além da tolerância
        S->>S: leituras_fora += 1
        alt leituras_fora >= 2
            S->>D: INSERT alerta (fora_da_area)
        end
    else dentro
        S->>D: resolve alerta de área, zera contador
    end

    alt atividade <= limiar por tempo demais
        S->>D: INSERT alerta (imovel)
    end

    A-->>G: 201 + estado do animal
```

## Ciclo de vida do alerta

```mermaid
stateDiagram-v2
    [*] --> Normal

    Normal --> ForaSuspeito: posição além da tolerância
    ForaSuspeito --> Normal: voltou (histerese absorve o erro do GNSS)
    ForaSuspeito --> ForaConfirmado: 2ª leitura consecutiva fora
    ForaConfirmado --> Normal: voltou para dentro

    Normal --> ParadoSuspeito: atividade <= 0.08
    ParadoSuspeito --> Normal: voltou a se mover
    ParadoSuspeito --> ParadoConfirmado: passou do tempo limite
    ParadoConfirmado --> Normal: voltou a se mover

    Normal --> SemSinal: silêncio > 4x a periodicidade
    ForaConfirmado --> SemSinal: silêncio
    SemSinal --> Normal: voltou a reportar

    note right of ForaSuspeito
        Estado intermediário é o
        que impede alarme falso
    end note
```

Os estados **suspeito** não geram notificação. São eles que separam "o GNSS
oscilou" de "o boi saiu".

## Autenticação

```mermaid
sequenceDiagram
    autonumber
    participant U as App
    participant A as API
    participant D as Banco

    rect rgba(46,158,99,0.08)
        Note over U,D: login
        U->>A: POST /auth/login (e-mail, senha)
        A->>D: conta bloqueada? (por e-mail e por IP)
        A->>A: Argon2id.verify
        A->>D: grava sessão (SHA-256 do refresh)
        A-->>U: access token (15 min, corpo)<br/>+ refresh (cookie HttpOnly)<br/>+ csrf (cookie legível)
    end

    rect rgba(139,111,203,0.10)
        Note over U,D: uso normal
        U->>A: GET /api/animais<br/>Authorization: Bearer
        A-->>U: 200
    end

    rect rgba(224,130,26,0.10)
        Note over U,D: renovação
        U->>A: GET /api/animais (token expirado)
        A-->>U: 401
        U->>A: POST /auth/refresh<br/>cookie + X-CSRF-Token
        A->>D: token já usado antes?
        alt reuso detectado
            A->>D: revoga a família inteira
            A-->>U: 401 — refazer login
        else válido
            A->>D: marca usado, cria o próximo
            A-->>U: access novo + refresh NOVO
        end
        U->>A: repete GET /api/animais
    end
```

Detalhe do desenho: o refresh **nunca** aparece no corpo da resposta. Se
aparecesse, o front teria de guardá-lo em algum lugar que o JavaScript lê, e um
XSS levaria a sessão de 14 dias junto.

## Camadas do backend

```mermaid
flowchart TD
    R["<b>api/routes/</b><br/>HTTP, códigos de status, validação de entrada"]
    P["<b>api/deps.py</b><br/>quem é você, o que pode fazer"]
    S["<b>services/</b><br/>regra de negócio"]
    M["<b>models.py</b><br/>ORM"]
    G["<b>security/</b><br/>senhas, tokens, chaves, limites, auditoria"]
    DB[("PostGIS")]

    R --> P
    R --> S
    P --> G
    S --> M
    S --> G
    M --> DB
```

Regra que orienta o corte: **rota não contém regra de negócio, e serviço não
conhece HTTP.** É o que permite o simulador e o endpoint de telemetria
compartilharem `services/telemetria.py` sem duplicar nada.

Autorização é declarada em `api/routes/__init__.py`, no `include_router`, não
rota a rota. Assim uma rota nova nasce protegida — para deixar algo aberto é
preciso adicioná-lo explicitamente ao grupo público, e isso aparece no diff.

## Frontend

```mermaid
flowchart TD
    App["<b>App.tsx</b><br/>estado, polling, portão de sessão"]
    Api["<b>api.ts</b><br/>HTTP, token em memória,<br/>renovação com single-flight"]
    Types["<b>types.ts</b><br/>espelho dos schemas"]

    Mapa["MapaView"]
    Folha["FolhaInferior"]
    Lista["ListaAnimais"]
    Feed["FeedAlertas"]
    Sim["PainelSimulacao"]
    Conta["PainelConta"]
    Login["TelaLogin"]

    App --> Api
    App --> Mapa
    App --> Folha
    Folha --> Lista
    Folha --> Feed
    Folha --> Sim
    Folha --> Conta
    App --> Login
    Api --> Types

    style Api fill:#1f4d3a,stroke:#2e9e63,color:#e6edf1
    style Types fill:#1f4d3a,stroke:#2e9e63,color:#e6edf1
```

`api.ts` e `types.ts` não importam nada do React de propósito: o app React
Native planejado reaproveita os dois sem alteração.

## Limites conhecidos

| Limite | Consequência | Quando resolver |
|---|---|---|
| `create_all` no lugar de migração | Mudança de schema exige recriar o banco | Antes do primeiro piloto com dados reais |
| Polling de 3 s | Tráfego constante; latência de até 3 s no alerta | Quando o número de clientes justificar WebSocket |
| Monofazenda | `GET /api/fazenda` devolve a primeira | Antes do segundo cliente |
| Sem push | O alerta só existe com o app aberto | É a promessa central do produto — próxima prioridade |
| Simulador embutido na API | Acoplamento entre demonstração e produção | Quando o hardware chegar |
| Uma réplica de API | O simulador e a manutenção duplicariam com 2+ réplicas | Antes de escalar horizontalmente |
