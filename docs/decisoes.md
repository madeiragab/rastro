> 🇧🇷 **Português** · [🇬🇧 English](decisions.md)

# Registro de decisões

Cada entrada segue o formato ADR: contexto, decisão, consequência. O que
interessa aqui é o **porquê** — o código já mostra o quê.

---

## ADR-001 — Brinco auricular, não implante subcutâneo

**Situação:** proposta inicial de um chip implantado no animal reportando
posição.

**Decisão:** descartar o implante. Usar brinco auricular.

**Motivo:** quatro barreiras independentes, e basta uma.

1. Tecido biológico atenua RF. O GPS civil opera em 1,575 GHz e o sinal que
   chega ao solo já está por volta de −130 dBm. Sob a pele, cai abaixo do
   limiar de detecção.
2. Antena eficiente pede cerca de um quarto do comprimento de onda — ~8 cm em
   915 MHz. Não cabe em cápsula implantável sem destruir o ganho.
3. Enlace de satélite exige pico de 1–2 W. Implante não tem sol, não permite
   troca de bateria, e recarga sem fio através de tecido é ineficiente.
4. Dispositivo em músculo é corpo estranho na carcaça — risco de rejeição pelo
   frigorífico. A Nexa Labs contorna colocando o chip **na orelha**, que é
   descartada no início do abate.

**Consequência:** todo o desenho assume dispositivo externo, com sol e
manutenção possível. Coincide com o ponto onde o PNIB já obriga identificação.

---

## ADR-002 — PostGIS, não cálculo geométrico em Python

**Situação:** o teste ponto-em-polígono roda a cada leitura, para cada animal.

**Decisão:** PostGIS. `ST_Contains` e `ST_Distance` no banco.

**Alternativa descartada:** Shapely em Python, com o polígono guardado como
JSON. Mais simples de subir — não exige imagem com extensão — mas obriga a
carregar todos os polígonos em memória a cada avaliação, não tem índice
espacial, e distância em graus não é distância em metros.

**Consequência:** dependência de imagem PostGIS. Em troca, a distância em metros
sai correta via `cast(geom, Geography)`, sem erro de projeção, e o índice
espacial já existe quando o rebanho crescer.

---

## ADR-003 — Zona de tolerância mais histerese na geocerca

**Situação:** GNSS de baixo consumo erra dezenas de metros. Animal pastando
junto à cerca cruza a linha o tempo todo, no dado.

**Decisão:** só considerar "fora" quando ultrapassar o polígono **e** estiver
além de 25 m dele, **e** isso se repetir em 2 leituras consecutivas.

**Consequência:** um animal que sai e volta rápido pode passar despercebido — e
está tudo bem. O custo de um alarme falso é muito maior que o de uma fuga curta
não detectada: **produtor que recebe alerta falso desinstala o aplicativo.**
Esse é o maior risco de adoção do produto, acima de qualquer questão técnica.

---

## ADR-004 — Imobilidade pelo acelerômetro, não pelo GNSS

**Situação:** detectar animal caído é o alerta de maior valor comercial —
detecta morte, parto travado, atolamento, fratura.

**Decisão:** decidir pelo índice de atividade do acelerômetro. O GNSS não entra
na regra.

**Motivo:** GNSS parado, sozinho, mente. Bovino deitado ruminando fica estático
por horas em condição perfeitamente normal. Uma regra baseada em GNSS geraria
alerta todo fim de tarde.

**Consequência:** o brinco **precisa** de acelerômetro. Custo desprezível no
componente, mas vira requisito de hardware não negociável.

---

## ADR-005 — Limiar relativo na perda de sinal

**Situação:** detectar brinco arrancado (furto), bateria morta ou animal em
grota sem propagação.

**Decisão:** o limiar é múltiplo da periodicidade esperada **daquele
dispositivo**, não um valor fixo global.

**Motivo:** a periodicidade varia por animal e por terreno. Um limiar único
geraria ruído constante nos dispositivos mais lentos e demoraria demais nos
mais rápidos.

**Consequência:** cada dispositivo precisa de uma linha de base. No MVP é
configuração global; com hardware real, passa a ser por dispositivo.

---

## ADR-006 — Endpoint único de telemetria

**Situação:** o hardware não existe. É preciso demonstrar o produto sem ele.

**Decisão:** simulador e gateway real entram pelo **mesmo** `services/telemetria.py`.
O simulador chama a função; o gateway chama `POST /api/telemetria`, que chama a
mesma função.

**Consequência:** trocar o simulador por hardware não muda nenhuma regra de
negócio — basta apontar o gateway e desligar `SIMULATOR_ENABLED`. O preço é o
simulador viver dentro da API, o que acopla demonstração e produção. Aceitável
enquanto o hardware não existe.

---

## ADR-007 — Autorização declarada no roteador, não rota a rota

**Situação:** rota nova esquecida sem proteção é uma das falhas mais comuns e
mais silenciosas.

**Decisão:** declarar a dependência de autenticação no `include_router`, em
`api/routes/__init__.py`, e não em cada função.

**Consequência:** rota nova nasce protegida. Para deixar algo aberto é preciso
movê-lo explicitamente para o grupo público — e isso aparece no diff, onde dá
para questionar.

---

## ADR-008 — Access token em memória, refresh em cookie HttpOnly

**Situação:** onde o navegador guarda a sessão.

**Decisão:** access token (15 min) só em memória do JavaScript. Refresh token
(14 dias) em cookie `HttpOnly` + `SameSite=strict`, com rotação e detecção de
reuso.

**Alternativas descartadas:**

| Opção | Por que não |
|---|---|
| Access em `localStorage` | Qualquer XSS lê e exfiltra |
| Refresh no corpo da resposta | Obriga o front a guardá-lo onde o JavaScript lê — mesmo problema |
| Só cookie de sessão, sem JWT | Simples, mas exige consulta ao banco a cada requisição e complica o app nativo do roadmap |

**Consequência:** recarregar a página perde o access token — e isso é
intencional. A sessão é restaurada por uma chamada de refresh na carga. Em
troca, XSS não leva a sessão de longa duração.

---

## ADR-009 — Argon2id nas senhas, SHA-256 nos refresh tokens

**Situação:** dois segredos, guardados de formas diferentes. Parece
inconsistência.

**Decisão:** Argon2id para senha, SHA-256 para refresh token.

**Motivo:** hash lento existe para proteger segredo de **baixa entropia** —
senha, que humano escolhe e atacante adivinha por dicionário. Um refresh token
tem 256 bits aleatórios: não existe dicionário a percorrer, então um hash rápido
já garante que um dump do banco não vire sessão válida. Usar Argon2 ali só
tornaria cada renovação mais lenta, sem ganho de segurança.

---

## ADR-010 — Mobile-first agora, React Native depois

**Situação:** o produto é para o produtor no campo, com o celular na mão.

**Decisão:** web mobile-first (PWA) para o MVP. React Native quando o produto
for validado.

**Motivo:** para apresentar, abrir por URL vence instalar app. Para o produto
real, push confiável nos dois sistemas exige nativo — e push é a promessa
central.

**Consequência:** `api.ts` e `types.ts` foram escritos sem importar nada do
React, para o app nativo reaproveitá-los sem alteração.

---

## ADR-011 — `create_all` no lugar de migrações, por enquanto

**Situação:** o schema ainda muda a cada sessão de trabalho.

**Decisão:** criar as tabelas por metadata na subida. Adiar o Alembic.

**Consequência:** **mudança de schema exige recriar o banco** (`docker compose
down -v`). Aceitável enquanto não há dado real. Vira dívida no instante em que o
primeiro piloto de campo começar — e está registrada como tal.

---

## ADR-012 — Polling de 3 segundos, não WebSocket

**Situação:** o painel precisa refletir a posição do rebanho quase em tempo real.

**Decisão:** polling simples a cada 3 s.

**Motivo:** com poucos clientes, o polling é trivial de acertar e não tem estado
de conexão para gerenciar — nem reconexão, nem heartbeat, nem sessão presa. Um
WebSocket mal reconectado é pior que polling.

**Consequência:** tráfego constante e latência de até 3 s. Trocar quando o número
de clientes justificar, não antes.

---

## ADR-013 — Contador de versão para invalidar token, não carimbo de tempo

**Situação:** trocar a senha precisa derrubar todo access token já emitido.

**Primeira tentativa:** comparar o `iat` do JWT com `senha_alterada_em` do
usuário. Token emitido antes da troca é recusado.

**Por que estava errado:** os dois valores têm resolução de **um segundo**.
Trocar a senha no mesmo segundo em que o token foi emitido deixava o token
anterior válido — e essa é exatamente a situação de quem acaba de descobrir a
invasão e corre para trocar a senha. A janela é pequena, mas está no pior
momento possível.

**Decisão:** contador `token_versao` no usuário, enviado no token como claim
`ver` e comparado por igualdade. Trocar a senha incrementa.

**Consequência:** sem granularidade, sem relógio, sem janela. Custa uma coluna
`integer` e uma comparação. Quem encontrou o problema foi a suíte de testes, na
primeira execução real — não a revisão de código, que leu o `<` e achou correto.
