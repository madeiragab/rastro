> 🇧🇷 **Português** · [🇬🇧 English](requirements.md)

# Documento de requisitos

**Produto:** Rastro — rastreamento em tempo real e geocerca para rebanho bovino
**Versão:** 0.2 (MVP)
**Data:** agosto de 2026

---

## 1. Contexto e problema

O pequeno e médio produtor de Minas Gerais não sabe onde está o rebanho. As
consequências têm custo direto:

- **Abigeato** (furto de gado): o produtor descobre dias depois, quando conta o
  lote. A essa altura o animal já foi abatido ou vendido.
- **Morte não percebida:** um animal caído por parto travado, atolamento ou
  fratura morre em horas. Achado a tempo, sobrevive.
- **Fuga por cerca rompida:** o gado sai para estrada ou lavoura do vizinho —
  risco de acidente e de conflito.
- **Busca manual:** encontrar um animal específico numa área de centenas de
  hectares consome dia de trabalho.

O estudo de viabilidade que precedeu este projeto ([contexto no
README](../README.pt-BR.md#contexto)) concluiu que a barreira nunca foi a
tecnologia de localização, e sim o **custo por cabeça** — que é dominado por
onde fica o rádio de longo alcance.

## 2. Personas

| Persona | Perfil | O que precisa | O que não tolera |
|---|---|---|---|
| **José, produtor** | 58 anos, 60 cabeças, celular Android intermediário, internet instável | Saber que algo deu errado sem abrir o app | Alarme falso. Dois seguidos e ele desinstala |
| **Marcos, vaqueiro** | 34 anos, trabalha em campo, usa o celular com uma mão só e luva | Achar rápido o animal no mapa | Interface que exige precisão de toque |
| **Ana, filha do produtor** | 27 anos, administra a fazenda, confortável com tecnologia | Relatório, histórico, controle de acesso | Ter que ensinar o pai a usar |

## 3. Escopo do MVP

### Dentro

Demarcação de pasto pelo mapa, monitoramento de posição, os três alertas,
autenticação, papéis de acesso e credencial de dispositivo.

### Fora — e por quê

| Item | Motivo |
|---|---|
| Firmware do brinco | Depende da decisão de conectividade, que depende de medição em campo |
| Notificação push | Exige app nativo para funcionar de forma confiável nos dois sistemas |
| Multi-fazenda | Só faz sentido a partir do segundo cliente |
| Relatório de ganho de peso | Não é o problema que trava a venda |
| Cerca virtual ativa (estímulo no animal) | Outro produto, outra regulação |

## 4. Requisitos funcionais

Prioridade: **must** (sem isso não há produto) · **should** (esperado) ·
**could** (desejável).

### 4.1 Demarcação

| ID | Requisito | Prioridade |
|---|---|---|
| RF-01 | O usuário desenha o polígono do pasto tocando vértices no mapa | must |
| RF-02 | O sistema calcula e exibe a área em hectares | should |
| RF-03 | Cada pasto tem zona de tolerância configurável (padrão 25 m) | must |
| RF-04 | Um pasto com animais vinculados não pode ser removido | should |

### 4.2 Monitoramento

| ID | Requisito | Prioridade |
|---|---|---|
| RF-05 | Exibir no mapa a última posição de cada animal, colorida por estado | must |
| RF-06 | Exibir a trilha recente do animal selecionado | should |
| RF-07 | Listar os animais ordenados por gravidade, não por nome | must |
| RF-08 | Exibir o nível de bateria de cada brinco | should |
| RF-09 | Receber telemetria de gateway externo por API | must |

### 4.3 Alertas

| ID | Requisito | Critério de aceite |
|---|---|---|
| RF-10 | **Fora da área** | Dispara somente após 2 leituras consecutivas além do polígono + tolerância. Uma leitura isolada fora **não** dispara |
| RF-11 | **Sem movimento** | Baseado no acelerômetro. Animal deitado ruminando com GNSS estático **não** dispara |
| RF-12 | **Perda de sinal** | Limiar relativo à periodicidade do próprio dispositivo, não valor fixo global |
| RF-13 | Alerta aberto não é reaberto enquanto não for resolvido | Uma ocorrência gera uma notificação, não uma por leitura |
| RF-14 | Alerta se resolve sozinho quando a causa cessa | Animal volta ao pasto → alerta de área fecha |
| RF-15 | O usuário pode marcar um alerta como resolvido | Se a causa persistir, reabre no ciclo seguinte |

### 4.4 Acesso

| ID | Requisito | Prioridade |
|---|---|---|
| RF-16 | Login por e-mail e senha | must |
| RF-17 | Três papéis: leitura, operador, dono | must |
| RF-18 | Troca de senha encerra todas as sessões, em todos os aparelhos | must |
| RF-19 | O dono gera e revoga chaves de gateway | must |
| RF-20 | Ações sensíveis ficam registradas em trilha de auditoria | should |

### 4.5 Matriz de permissões

| Ação | leitura | operador | dono |
|---|:---:|:---:|:---:|
| Ver mapa, animais e alertas | ✅ | ✅ | ✅ |
| Resolver alerta | ✅ | ✅ | ✅ |
| Criar e remover pasto | ❌ | ✅ | ✅ |
| Forçar cenário de simulação | ❌ | ✅ | ✅ |
| Gerar e revogar chave de gateway | ❌ | ❌ | ✅ |

## 5. Requisitos não funcionais

### 5.1 Usabilidade

| ID | Requisito | Verificação |
|---|---|---|
| RNF-01 | Mobile-first: projetado para tela de celular, adaptado para desktop | Layout de coluna única até 900 px |
| RNF-02 | Alvos de toque de no mínimo 44 px | Inspeção do CSS |
| RNF-03 | Operável com uma das mãos | Controles principais na metade inferior |
| RNF-04 | O mapa não se move sozinho ao chegar posição nova | Só recentraliza na troca de animal |
| RNF-05 | Interface em português, sem jargão técnico | Revisão de texto |

### 5.2 Confiabilidade

| ID | Requisito |
|---|---|
| RNF-06 | Taxa de alarme falso próxima de zero — é o critério que decide a adoção |
| RNF-07 | Falha do gateway não perde dado: o brinco acumula e descarrega depois (aceita telemetria com até 7 dias de atraso) |
| RNF-08 | A API tolera o banco indisponível na subida, com espera e nova tentativa |

### 5.3 Segurança

Detalhamento em [segurança](seguranca.md).

| ID | Requisito |
|---|---|
| RNF-09 | Senha guardada com Argon2id, nunca em texto ou hash rápido |
| RNF-10 | Sessão de longa duração inacessível ao JavaScript (cookie HttpOnly) |
| RNF-11 | Refresh token com rotação e detecção de reuso |
| RNF-12 | Proteção contra força bruta por conta **e** por IP |
| RNF-13 | Gateway autenticado por credencial própria, revogável sem afetar contas de pessoas |
| RNF-14 | A aplicação se recusa a subir em produção com configuração insegura |
| RNF-15 | Resposta de erro não revela se um e-mail existe |

### 5.4 Desempenho

| ID | Requisito | Alvo |
|---|---|---|
| RNF-16 | Tempo de resposta das consultas do painel | < 300 ms com 200 animais |
| RNF-17 | Latência entre a leitura chegar e o alerta abrir | < 1 ciclo de leitura |
| RNF-18 | Teste ponto-em-polígono no banco, com índice espacial | Sem varredura completa |

### 5.5 Portabilidade

| ID | Requisito |
|---|---|
| RNF-19 | Sobe com um comando (`docker compose up`) em qualquer sistema com Docker |
| RNF-20 | Camada de rede do frontend independente de framework, reaproveitável no React Native |

## 6. Restrições

| Restrição | Origem |
|---|---|
| Custo por cabeça abaixo de R$ 150 no cenário de entrada | Capacidade de compra do pequeno produtor |
| Brinco de 15 dígitos com prefixo `076` | PNIB — identificação individual obrigatória a partir de 2033 |
| O dispositivo pode ficar dias sem cobertura | Relevo de Minas Gerais |
| Sem chave de API paga no mapa | Custo por usuário; daí OpenStreetMap |
| O implante está descartado | Física: tecido atenua RF, antena não cabe, energia não se sustenta |

## 7. Regras de negócio

| ID | Regra |
|---|---|
| RN-01 | Um animal pertence a no máximo um pasto por vez |
| RN-02 | Um gateway só reporta posição de animais da própria fazenda |
| RN-03 | Posição com carimbo no futuro (> 5 min) ou antigo demais (> 7 dias) é recusada |
| RN-04 | A chave de gateway é exibida uma única vez, na criação |
| RN-05 | Chave revogada não é apagada, para a auditoria continuar legível |
| RN-06 | Access token emitido antes da última troca de senha é inválido |

## 8. Glossário

| Termo | Significado |
|---|---|
| **Abigeato** | Furto de gado. Crime tipificado no Código Penal brasileiro |
| **Brinco** | Identificador preso à orelha do animal. Aqui, eletrônico |
| **Geocerca** | Perímetro virtual; o sistema avisa quando é cruzado |
| **GNSS** | Nome genérico dos sistemas de posicionamento por satélite (GPS é um deles) |
| **Histerese** | Exigir confirmação antes de mudar de estado, para não oscilar no limiar |
| **LoRa** | Rádio de longo alcance e baixo consumo, em faixa livre de 915 MHz |
| **NB-IoT** | Rede celular dedicada a IoT, de baixo consumo |
| **NTN** | *Non-Terrestrial Network* — extensão do 5G que permite falar com satélite |
| **PNIB** | Plano Nacional de Identificação Individual de Bovinos e Búfalos |
| **Gateway** | Equipamento que recebe os brincos por rádio e repassa à internet |

## 9. Critérios de aceite do MVP

O MVP está pronto para demonstração quando:

1. ✅ O produtor desenha um pasto pelo celular e ele aparece no mapa
2. ✅ Os animais se movem no mapa em tempo real
3. ✅ Forçar fuga gera alerta de área em menos de 30 s
4. ✅ Forçar imobilidade gera alerta em menos de 2 min
5. ✅ Forçar silêncio gera alerta de perda de sinal em menos de 2 min
6. ✅ Nenhum alerta falso durante 10 min de pastejo normal
7. ✅ O acesso exige login, e o gateway exige chave própria
8. ⬜ **Verificado em execução real** — pendente: ver [estado atual](../README.pt-BR.md#status)

Os itens 1 a 7 estão implementados e verificados por análise estática. O item 8
é o que falta: a aplicação ainda não foi executada de ponta a ponta.
