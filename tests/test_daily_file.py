import sys
import os
sys.path.append(os.path.abspath('.'))

import config
from analyzer import analizar_dia
import bot

analyses = analizar_dia()

with open('test_output.txt', 'w', encoding='utf-8') as f:
    if not analyses:
        f.write("No hay partidos hoy.\n")
    else:
        msg = bot.mensaje_analisis_manana(analyses)
        f.write(msg)
