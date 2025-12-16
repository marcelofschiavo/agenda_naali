import base64

# Substitua pelo caminho real da sua imagem
caminho_imagem = "logonaalli.jpg" 

with open(caminho_imagem, "rb") as image_file:
    encoded_string = base64.b64encode(image_file.read()).decode()

print(encoded_string)