import os

# Path of dir containing file to re-convert
dir = "./guidelines"

for filename in os.listdir(dir):
    if filename.endswith(".txt"):
        path_file = os.path.join(dir, filename)

        try:
            # Try to open with automatic encoding
            with open(path_file, 'r', encoding='utf-8') as file:
                content = file.read()
        except UnicodeDecodeError:
            # If it fails, read with cp1252 encoding
            with open(path_file, 'r', encoding='cp1252') as file:
                content = file.read()

        # Overwrite file in UTF-8
        with open(path_file, 'w', encoding='utf-8') as file:
            file.write(content)

        print(f"{filename} converted in UTF-8.")
