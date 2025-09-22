import os

# Percorso della cartella dove si trovano i file da riconvertire
cartella = "./guidelines"

for filename in os.listdir(cartella):
    if filename.endswith(".txt"):
        percorso_file = os.path.join(cartella, filename)

        try:
            # Prova ad aprire con encoding automatico (sistema operativo)
            with open(percorso_file, 'r', encoding='utf-8') as file:
                contenuto = file.read()
        except UnicodeDecodeError:
            # Se fallisce, prova con Windows-1252
            with open(percorso_file, 'r', encoding='cp1252') as file:
                contenuto = file.read()

        # Sovrascrive il file in UTF-8
        with open(percorso_file, 'w', encoding='utf-8') as file:
            file.write(contenuto)

        print(f"{filename} convertito in UTF-8.")
