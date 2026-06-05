import sys
import os
sys.path.append(os.path.abspath('.'))

import config
from analyzer import analizar_dia
import bot

# Force output to stdout
print("Corriendo análisis del día para prueba...\n")
analyses = analizar_dia()

if not analyses:
    print("No hay partidos hoy.")
else:
    msg = bot.mensaje_analisis_manana(analyses)
    print("\n" + "="*50)
    print("MENSAJE QUE SE ENVIARÍA A TELEGRAM:")
    print("="*50)
    print(msg)
    print("="*50)
