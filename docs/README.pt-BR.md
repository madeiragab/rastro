# Rastro — documentação

[🇬🇧 English](README.md) · **🇧🇷 Português**

| Documento | O que cobre |
|---|---|
| [Requisitos](requisitos.md) | Problema, personas, requisitos funcionais e não funcionais, matriz de permissões, regras de negócio, glossário, critérios de aceite |
| [Arquitetura](arquitetura.md) | Diagramas de contexto e containers, modelo ER, sequência de telemetria e autenticação, máquina de estados do alerta, camadas, limites conhecidos |
| [Segurança](seguranca.md) | Modelo de ameaça, STRIDE, cada controle implementado com o motivo, e a lista honesta do que **não** está protegido |
| [Registro de decisões](decisoes.md) | 16 ADRs: o que foi decidido, o que foi descartado, e por quê |
| [Implantação](implantacao.md) | Colocar no ar num servidor Linux: domínio, TLS, SMTP, backup, atualização — e o que ainda falta para ser infraestrutura madura |
| [Arquitetura de hardware](arquitetura-hardware.md) | O lado do campo, que ainda não existe: malha de rádio no rebanho, geocerca rodando no brinco, três mestres em rodízio, autonomia de bateria, custo unitário e preço |
| [Protocolo dos dispositivos](protocolo-dispositivos.md) | O que as placas falam com o servidor: ciclo do brinco e do mestre, endpoints, máquina de estados da eleição — é contra este documento que o firmware será escrito |

Comece pelo [README da raiz](../README.pt-BR.md) para instruções de execução e
demonstração.

---

## Ordem de leitura

**Para entender o produto** → Requisitos, seções 1 a 3.

**Para revisar o código** → Arquitetura (camadas), depois o Registro de decisões.

**Para avaliar a postura de segurança** → Segurança, em especial
["O que NÃO está protegido"](seguranca.md#o-que-não-está-protegido).

**Para continuar o desenvolvimento** → Arquitetura (limites conhecidos) mais
ADR-011 e ADR-012, que descrevem a dívida assumida de propósito.

## Diagramas

Todos os diagramas são Mermaid dentro do Markdown — o GitHub renderiza
nativamente. Não há arquivo de imagem para manter em sincronia com o código, e o
diagrama é editado no mesmo commit da mudança que ele descreve.
