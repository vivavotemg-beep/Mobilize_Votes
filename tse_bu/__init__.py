"""Coletor de Boletins de Urna (bweb) do TSE para qualquer município brasileiro.

Eleições gerais/municipais: baixa o arquivo oficial de Boletim de Urna da UF,
filtra o município e o cargo desejados, gera um PDF de boletim por urna,
um CSV consolidado com ranking de abstenção e um indicador de
"potencial de virada" para o segundo turno.
"""

__version__ = "1.0.0"
