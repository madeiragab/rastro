> 🇧🇷 **Português** · [🇬🇧 English](security.md)

# Segurança

Como o Rastro se defende, de que se defende, e — igualmente importante — do que
**não** se defende.

> **Aviso.** Este é um projeto de MVP. O desenho segue boas práticas correntes,
> mas **nunca passou por auditoria externa nem por teste de intrusão**. Os
> controles abaixo têm teste automatizado, mas teste só prova o comportamento que
> alguém pensou em verificar. Não trate como sistema endurecido.

---

## Modelo de ameaça

Quem realisticamente ataca um sistema destes:

| Agente | Motivação | Capacidade |
|---|---|---|
| **Ladrão de gado** | Saber onde está o gado; apagar o rastro do furto | Baixa. Mas o dano é direto e imediato |
| **Curioso na mesma rede** | Xeretar o app do vizinho | Baixa |
| **Varredura automatizada** | Qualquer coisa exposta na internet | Média, e incessante |
| **Ex-funcionário** | Sabotagem, acesso após o desligamento | Média. **Conhece as credenciais** |
| **Concorrente** | Dados do rebanho, movimentação, engorda | Média a alta |

Ameaça que muda o desenho: **o ladrão de gado é o adversário que mais importa**.
Ele não precisa invadir a nuvem — basta arrancar o brinco. Por isso a perda de
sinal é um alerta de primeira classe, e não um detalhe de infraestrutura.

## STRIDE

| Categoria | Ameaça concreta | Controle |
|---|---|---|
| **S**poofing | Alguém se passa pelo gateway e injeta posição falsa para esconder um furto | Chave de API por gateway, Argon2id, revogável; a chave só vale para animais da própria fazenda |
| **T**ampering | Reescrever a trilha do passado ou empurrar o carimbo para o futuro e silenciar o alerta de silêncio | Validação de faixa temporal (+5 min / −7 dias) na entrada |
| **R**epudiation | "Não fui eu que revoguei a chave" | Trilha de auditoria com usuário, ação, IP e horário |
| **I**nformation disclosure | Descobrir quais e-mails existem; ler a sessão de outro | Resposta genérica no login, tempo constante, cookie HttpOnly, CSP fechada |
| **D**enial of service | Marretar o login até travar; senha gigante para estourar o custo do Argon2 | Bloqueio por conta e por IP; senha limitada a 128 caracteres |
| **E**levation of privilege | Operador vira dono; token forjado | Papéis verificados no servidor; JWT com algoritmo fixo e claims obrigatórias |

## Controles implementados

### Senha

Argon2id, 64 MiB de memória, 3 iterações, paralelismo 2 — acima do mínimo do
OWASP (19 MiB, t=2).

Por que não bcrypt: o custo do bcrypt é só de CPU e sua memória é fixa e
pequena, o que o torna barato de atacar com GPU e ASIC. O custo de memória do
Argon2id é justamente o que encarece esse ataque.

Política pelo NIST SP 800-63B: **comprimento mínimo de 12 e lista de bloqueio,
sem regras de composição**. Exigir "uma maiúscula e um símbolo" produz
`Senha@123` — curta, previsível e péssima.

Senha normalizada em NFKC antes do hash. Sem isso, a mesma senha digitada no
teclado do celular e no teclado físico pode gerar bytes diferentes e trancar o
usuário para fora sem explicação.

Reidratação automática: se os parâmetros de custo aumentarem, o hash é
regravado no login seguinte — o único instante em que a senha em claro existe.

### Sessão

```
access token   JWT HS256, 15 min, no corpo, guardado só em memória
refresh token  256 bits opacos, 14 dias, cookie HttpOnly + SameSite=strict
```

**Por que dois tokens.** O access é autocontido e rápido de validar, mas não dá
para revogar antes de expirar — daí a vida curta. O refresh é revogável a
qualquer momento, e por isso pode durar.

**Por que o refresh não vai no corpo da resposta.** Se fosse, o front teria de
guardá-lo onde o JavaScript lê, e um XSS levaria a sessão de 14 dias junto. Em
cookie HttpOnly, o script da página não o alcança.

**Por que o access fica só em memória.** `localStorage` e `sessionStorage` são
legíveis por qualquer XSS. Em memória, o token morre com a aba, e a sessão é
restaurada na próxima carga pelo cookie.

**Rotação com detecção de reuso.** Cada uso do refresh emite um novo e marca o
anterior como usado. Se um token já usado reaparecer, a única explicação é que
existem duas cópias — e não há como saber qual delas é a legítima. A família
inteira é revogada e ambos os lados precisam refazer login. É a recomendação do
*OAuth 2.0 Security BCP* para clientes públicos.

**Guarda no banco: SHA-256, não Argon2.** Argon2 é caro de propósito para
proteger segredo de baixa entropia, que humano escolhe e atacante adivinha. Um
token de 256 bits aleatórios não tem dicionário a percorrer — um hash rápido já
garante que um dump do banco não vire sessão válida.

**Troca de senha derruba tudo.** As sessões são revogadas e todo access token já
emitido passa a ser recusado. Quem troca a senha por suspeita de invasão espera
exatamente isso: o invasor perde o acesso agora, não daqui a 14 dias.

O mecanismo é um contador `token_versao` no usuário, levado no token como claim
`ver` e comparado por igualdade. A primeira implementação comparava o `iat` do
JWT com `senha_alterada_em` — ambos com resolução de um segundo, então trocar a
senha no mesmo segundo do login deixava o token anterior válido. Um contador não
tem resolução a perder. Quem pegou isso foi a suíte de testes.

### CSRF

Duas camadas. `SameSite=strict` faz o navegador não enviar o cookie em
requisição originada de outro site — o que já barra a maior parte dos casos.
Sobre isso, *double-submit*: um cookie legível pelo JavaScript cujo valor
precisa ser repetido no header `X-CSRF-Token`, comparado em tempo constante. Um
site de terceiros consegue provocar o envio do cookie, mas não consegue ler seu
valor para preencher o header.

O cookie de refresh tem `Path=/api/auth`: nem acompanha as demais rotas.

### Força bruta

Contagem em banco (sobrevive a reinício e funciona com várias réplicas), em duas
trilhas:

- **por e-mail** — 5 falhas em 15 min bloqueiam por 15 min. Barra o ataque
  dirigido a uma conta.
- **por IP** — limite 4× mais folgado. Barra o *password spraying*, que testa
  uma senha comum contra muitas contas e nunca acumula falhas no mesmo e-mail.
  A folga existe porque uma fazenda inteira pode sair por um único IP.

O bloqueio conta a partir da **última** falha: insistir durante o bloqueio
empurra a liberação para frente.

### Enumeração de usuário

Três defesas juntas, porque uma só não basta:

1. Mensagem idêntica para e-mail inexistente, senha errada e conta desativada;
2. Quando o e-mail não existe, um hash descartável é verificado assim mesmo,
   para o tempo de resposta ficar igual;
3. O bloqueio por tentativas vale também para e-mails que não existem.

### Gateway

Formato `rastro_gw_<prefixo>_<segredo>`. O prefixo é público e indexado; o
segredo só existe como hash.

O prefixo não é enfeite: sem ele seria preciso verificar o hash Argon2 de
**todas** as chaves cadastradas a cada leitura de telemetria — e o Argon2 é caro
de propósito. Com o prefixo, é uma busca indexada e uma única verificação.

A chave completa aparece **uma vez**, na criação. Depois só o hash existe.
Revogar não apaga o registro, para a auditoria continuar legível.

Escopo: a chave é da fazenda. Um gateway não move o gado de outra propriedade.
Tentativa nesse sentido responde 404 — e não 403, que confirmaria a existência
do brinco para quem estivesse sondando.

### Cabeçalhos e transporte

`Content-Security-Policy: default-src 'none'` na API (que só devolve JSON),
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, COOP e CORP em `same-origin`,
`Cache-Control: no-store` nas rotas autenticadas, HSTS quando sob HTTPS.

CORS com lista explícita de origens. `allow_origins=["*"]` com credenciais é
recusado pelo navegador — e se não fosse, seria convite a roubo de sessão a
partir de qualquer site.

### Configuração

A aplicação **se recusa a subir** em `AMBIENTE=producao` se: a `SECRET_KEY` for
a de exemplo ou tiver menos de 32 bytes; `COOKIE_SECURE` for falso; houver
origem `http://` não-local no CORS; ou o simulador estiver ligado.

Fora de produção, um aviso no log deixa claro que os tokens são forjáveis.

Não existe senha default no código. A conta inicial usa `ADMIN_SENHA` do
ambiente ou, se vazia, uma senha sorteada e exibida no log **uma única vez**.
Credencial default versionada é como a maior parte dos sistemas expostos cai.

### Entrada

Faixas validadas no schema, não no banco: latitude −90..90, longitude −180..180,
atividade 0..1, bateria 0..100, brinco só dígitos com no máximo 15. É entrada de
rede vinda de dispositivo em campo, que pode estar com firmware velho, com
defeito, ou sob controle de terceiros.

Consultas via SQLAlchemy com parâmetros — sem concatenação de SQL em lugar
nenhum, inclusive nas chamadas PostGIS.

## O que NÃO está protegido

Lista honesta. Cada item é uma decisão consciente de MVP, não um esquecimento.

| Lacuna | Risco | O que fazer antes de produção |
|---|---|---|
| **HTTPS opcional** | O perfil `tls` existe e usa certificado de autoridade local; por padrão o compose serve HTTP | Domínio real com Let's Encrypt e `COOKIE_SECURE=true` |
| **Sem segundo fator** | Senha vazada = acesso total | TOTP ao menos para o papel `dono` |
| **Sem SMTP** | A recuperação de senha funciona, mas o link vai para o log da API em vez do e-mail | Plugar provedor em `services/notificacao.py` |
| **Sem rate limit geral** | Só login e recuperação de senha são limitados; o resto da API não | Limite por IP na borda |
| **Push sem confirmação de entrega** | O serviço do fabricante aceita e pode não entregar; o sistema não sabe | Reconciliação, ou canal secundário para alerta crítico |
| **Lista de senhas fraca** | ~30 itens, ilustrativa | Top 100k do HIBP, ou API de senhas vazadas com k-anonimato |
| **Auditoria sem retenção definida** | Cresce sem limite; sem política de exportação | Definir retenção e destino externo |
| **Segredo em variável de ambiente** | Visível em `docker inspect` e no histórico do shell | Gerenciador de segredos (Vault, SSM, Secret Manager) |
| **Sem revogação de access token** | Token roubado vale por até 15 min | Aceitável pelo prazo curto; se não for, lista de `jti` revogados |
| **`X-Forwarded-For` ignorado** | Atrás de proxy, o bloqueio por IP vê só o proxy | Habilitar quando houver proxy **confiável** declarado |
| **Sem verificação de e-mail** | Conta criada com endereço de terceiro | Confirmação por link |
| **Sem backup nem plano de recuperação** | Perda total do banco | Backup automatizado com restauração testada |
| **Dependências sem varredura** | CVE conhecida passa despercebida | Dependabot + `pip-audit` + `npm audit` no CI |

## Se você encontrar uma falha

Abra uma issue **sem detalhes técnicos do exploit** pedindo contato, ou escreva
direto para o dono do repositório. Este é um projeto pessoal, sem programa de
recompensa e sem SLA de resposta.

## Referências

- OWASP — *Password Storage Cheat Sheet*
- OWASP — *Session Management Cheat Sheet*
- NIST SP 800-63B — *Digital Identity Guidelines: Authentication*
- RFC 9700 — *Best Current Practice for OAuth 2.0 Security*
- RFC 6819 — *OAuth 2.0 Threat Model and Security Considerations*
