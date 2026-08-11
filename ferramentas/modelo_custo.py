#!/usr/bin/env python3
"""Modelo de custo e preço do sistema de rastreamento.

    python ferramentas/modelo_custo.py
    python ferramentas/modelo_custo.py --cabecas 200 --lotes 5

TODOS os valores abaixo sao estimativa de engenharia, nao cotacao. Existem para
ser substituidos: quando chegar preco real de fornecedor, troque a constante e
rode de novo. E por isso que isto e um script com variaveis nomeadas, e nao uma
tabela colada na documentacao -- tabela envelhece em silencio.

Fonte do preco da arroba: CEPEA/ESALQ, boi gordo Minas Gerais, 10/08/2026.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

# ===========================================================================
# Premissas -- troque por cotacao real conforme for conseguindo
# ===========================================================================

# --- composicao do brinco, em escala de milhares de unidades [EST] ---------
COMPONENTES_COMUM: dict[str, float] = {
    "MCU + radio LoRa (SX1262)": 25.0,
    "GNSS": 25.0,
    "Acelerometro": 4.0,
    "Bateria + celula solar": 20.0,
    "PCB + montagem": 18.0,
    "Encapsulamento + pino": 18.0,
}

# O mestre e o brinco comum mais isto. A unica diferenca real e o modem; o
# resto acompanha porque ele consome mais.
ADICIONAL_MESTRE: dict[str, float] = {
    "Modem celular (SIM7080G)": 55.0,
    "Bateria e celula maiores": 20.0,
    "PCB e montagem maiores": 15.0,
}

# Quanto o custo unitario e multiplicado numa primeira leva pequena: PCB de
# lote pequeno, montagem manual, molde nao amortizado.
FATOR_PILOTO = 2.5

# --- operacao --------------------------------------------------------------
CHIP_M2M_MENSAL = 10.0          # plano M2M de baixo trafego, por mestre
SERVIDOR_MENSAL = 20.0          # VPS rateado por cliente

# --- preco de venda --------------------------------------------------------
PRECO_EQUIPAMENTO_CABECA = 280.0
PRECO_INSTALACAO = 2000.0
PRECO_SERVICO_CABECA_MES = 5.0

# --- valor em risco (o argumento de venda) ---------------------------------
ARROBA_BOI_GORDO_MG = 331.0     # CEPEA 10/08/2026
DESCONTO_VACA_ARROBA = 32.0     # vaca gorda fica ~R$30-35 abaixo do boi
ARROBAS_POR_VACA = 16.0

# --- custo de entrada do negocio (nao entra no preco do cliente) -----------
NRE = {
    "Projeto de PCB e antena": (80_000.0, 200_000.0),
    "Homologacao Anatel": (30_000.0, 80_000.0),
}


@dataclass
class Cenario:
    """Uma propriedade. Lotes que nao se ouvem por radio precisam cada um dos
    seus mestres -- e por isso que `mestres_por_lote` multiplica por `lotes`."""

    cabecas: int = 60
    lotes: int = 3
    mestres_por_lote: int = 3

    @property
    def mestres(self) -> int:
        return self.lotes * self.mestres_por_lote

    @property
    def comuns(self) -> int:
        return max(0, self.cabecas - self.mestres)


@dataclass
class Custos:
    comum_escala: float = field(init=False)
    mestre_escala: float = field(init=False)
    comum_piloto: float = field(init=False)
    mestre_piloto: float = field(init=False)

    def __post_init__(self) -> None:
        self.comum_escala = sum(COMPONENTES_COMUM.values())
        self.mestre_escala = self.comum_escala + sum(ADICIONAL_MESTRE.values())
        self.comum_piloto = self.comum_escala * FATOR_PILOTO
        self.mestre_piloto = self.mestre_escala * FATOR_PILOTO


def reais(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def linha(titulo: str = "", largura: int = 66) -> None:
    if titulo:
        print(f"\n{titulo}")
        print("-" * largura)
    else:
        print("=" * largura)


def relatorio(cenario: Cenario) -> None:
    c = Custos()

    linha()
    print(f" RASTRO -- modelo de custo  |  {cenario.cabecas} cabecas, "
          f"{cenario.lotes} lotes, {cenario.mestres} mestres")
    linha()

    # ---------------------------------------------------------- unitario
    linha("CUSTO UNITARIO")
    print(f"{'':28} {'piloto':>14} {'escala':>14} {'por mes':>10}")
    print(f"{'Brinco comum':28} {reais(c.comum_piloto):>14} "
          f"{reais(c.comum_escala):>14} {reais(0):>10}")
    print(f"{'Brinco-mestre':28} {reais(c.mestre_piloto):>14} "
          f"{reais(c.mestre_escala):>14} {reais(CHIP_M2M_MENSAL):>10}")
    print(f"\n  O mestre custa {reais(c.mestre_escala - c.comum_escala)} a mais "
          f"em escala.")
    print("  So o mestre tem mensalidade: e o unico com chip.")

    # -------------------------------------------------------------- total
    hw_piloto = cenario.comuns * c.comum_piloto + cenario.mestres * c.mestre_piloto
    hw_escala = cenario.comuns * c.comum_escala + cenario.mestres * c.mestre_escala
    mensal_custo = cenario.mestres * CHIP_M2M_MENSAL + SERVIDOR_MENSAL

    linha("CUSTO DO SISTEMA")
    print(f"{'':28} {'piloto':>14} {'escala':>14}")
    print(f"{f'{cenario.comuns} brincos comuns':28} "
          f"{reais(cenario.comuns * c.comum_piloto):>14} "
          f"{reais(cenario.comuns * c.comum_escala):>14}")
    print(f"{f'{cenario.mestres} brincos-mestre':28} "
          f"{reais(cenario.mestres * c.mestre_piloto):>14} "
          f"{reais(cenario.mestres * c.mestre_escala):>14}")
    print(f"{'Hardware':28} {reais(hw_piloto):>14} {reais(hw_escala):>14}")
    print(f"{'Por cabeca':28} {reais(hw_piloto / cenario.cabecas):>14} "
          f"{reais(hw_escala / cenario.cabecas):>14}")
    print(f"\n{'Custo mensal':28} {reais(mensal_custo):>14}  "
          f"({cenario.mestres} chips + servidor)")

    # -------------------------------------------------------------- preco
    receita_equip = cenario.cabecas * PRECO_EQUIPAMENTO_CABECA
    receita_mensal = cenario.cabecas * PRECO_SERVICO_CABECA_MES

    linha("PRECO AO PRODUTOR")
    print(f"{'Equipamento':28} {reais(receita_equip):>14}  "
          f"({reais(PRECO_EQUIPAMENTO_CABECA)}/cabeca)")
    print(f"{'Instalacao':28} {reais(PRECO_INSTALACAO):>14}")
    print(f"{'Entrada total':28} {reais(receita_equip + PRECO_INSTALACAO):>14}")
    print(f"{'Servico mensal':28} {reais(receita_mensal):>14}  "
          f"({reais(PRECO_SERVICO_CABECA_MES)}/cabeca)")

    # ------------------------------------------------------------- margem
    linha("MARGEM")
    for nome, hw in (("Piloto", hw_piloto), ("Escala", hw_escala)):
        margem = receita_equip + PRECO_INSTALACAO - hw
        sinal = "" if margem >= 0 else "  <-- prejuizo"
        print(f"{nome + ' -- entrega':28} {reais(margem):>14}{sinal}")
    print(f"{'Recorrente':28} {reais(receita_mensal - mensal_custo):>14} / mes")

    # ------------------------------------------------- retorno do produtor
    valor_vaca = (ARROBA_BOI_GORDO_MG - DESCONTO_VACA_ARROBA) * ARROBAS_POR_VACA
    anual = receita_mensal * 12
    linha("RETORNO PARA O PRODUTOR")
    print(f"{'Valor de uma vaca':28} {reais(valor_vaca):>14}  "
          f"({ARROBAS_POR_VACA:.0f}@ x {reais(ARROBA_BOI_GORDO_MG - DESCONTO_VACA_ARROBA)})")
    print(f"{'Rebanho em risco':28} {reais(valor_vaca * cenario.cabecas):>14}")
    print(f"{'Custo anual do sistema':28} {reais(anual):>14}  "
          f"= {anual / valor_vaca:.2f} vaca")
    print(f"\n  Se evitar {anual / valor_vaca:.2f} perda por ano, se paga.")

    # ---------------------------------------------------------------- NRE
    linha("CUSTO DE ENTRADA DO NEGOCIO (nao entra no preco do cliente)")
    for nome, (minimo, maximo) in NRE.items():
        print(f"{nome:28} {reais(minimo):>14} a {reais(maximo)}")

    linha()
    print(" Todos os valores sao ESTIMATIVA, nao cotacao.")
    print(" Alcance do radio decide `mestres_por_lote` -- e o maior risco aqui.")
    linha()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cabecas", type=int, default=60)
    p.add_argument("--lotes", type=int, default=3)
    p.add_argument("--mestres-por-lote", type=int, default=3)
    args = p.parse_args()

    relatorio(Cenario(args.cabecas, args.lotes, args.mestres_por_lote))


if __name__ == "__main__":
    main()
