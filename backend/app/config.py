"""Configuracao central da aplicacao.

Todos os limiares do motor de alertas ficam aqui, e nao espalhados pelo codigo,
porque eles sao o principal ponto de calibragem quando o produto vai a campo.

Os valores default estao COMPRIMIDOS para demonstracao: um alerta que na
operacao real levaria horas dispara em segundos, para que o MVP seja
apresentavel em poucos minutos. As constantes `*_PRODUCAO` documentam o valor
que faz sentido no campo.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---------------------------------------------------------------- infra
    database_url: str = "postgresql+psycopg://rastro:rastro@localhost:5432/rastro"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # ------------------------------------------------------------ geocerca
    # Zona de tolerancia. O animal so e considerado fora quando ultrapassa o
    # poligono E esta buffer_m alem dele. Sem isso, o erro do GNSS gera alarme
    # falso continuo com o animal pastando junto a cerca.
    geofence_buffer_m: float = 25.0

    # Numero de leituras consecutivas fora antes de abrir o alerta (histerese).
    geofence_confirmacoes: int = 2

    # ----------------------------------------------------------- imobilidade
    # Indice de atividade (0..1) derivado do acelerometro. Abaixo disso o
    # animal e considerado sem movimento de cabeca.
    imobilidade_atividade_max: float = 0.08
    imobilidade_segundos: int = 90          # demo
    imobilidade_segundos_producao: int = 4 * 3600

    # --------------------------------------------------------- perda de sinal
    # Cada dispositivo tem sua propria periodicidade esperada. O alerta abre
    # quando o silencio passa de N vezes essa periodicidade -- limiar fixo
    # global geraria ruido, porque a periodicidade varia por animal e terreno.
    sinal_fator_silencio: float = 4.0
    sinal_silencio_minimo_s: int = 60

    # ------------------------------------------------------------- simulador
    simulator_enabled: bool = True
    simulator_tick_s: float = 4.0

    # Periodicidade nominal de reporte de cada brinco, em segundos.
    # Em campo seria 1800 (30 min), como o brinco solar da concorrencia.
    intervalo_reporte_s: int = 8
    intervalo_reporte_s_producao: int = 1800


settings = Settings()
