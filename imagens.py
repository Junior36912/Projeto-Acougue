"""Miniaturas das fotos de produto.

As fotos originais chegam a 2500 px e 2 MB, mas as telas as mostram com 50 a
200 px. Cada foto ganha uma miniatura WebP de até TAMANHO_MINIATURA px em
<pasta das fotos>/miniaturas/<nome da foto>.webp, e as telas usam a miniatura
quando ela existe. As miniaturas podem ser recriadas a qualquer momento a
partir das originais, por isso ficam fora do git e dos backups.
"""
import logging
import os

from PIL import Image, ImageOps

PASTA_MINIATURAS = 'miniaturas'
TAMANHO_MINIATURA = (320, 320)


def caminho_miniatura(pasta_fotos, foto):
    # O nome inteiro da foto entra no nome da miniatura: picanha.png e
    # picanha.webp não podem gerar o mesmo arquivo
    return os.path.join(pasta_fotos, PASTA_MINIATURAS, os.path.basename(foto) + '.webp')


def gerar_miniatura(pasta_fotos, foto):
    """Cria a miniatura (ou refaz, se a foto for mais nova que ela).
    Retorna o caminho da miniatura, ou None se a foto não puder ser lida."""
    origem = os.path.join(pasta_fotos, os.path.basename(foto))
    destino = caminho_miniatura(pasta_fotos, foto)
    try:
        if os.path.exists(destino) and os.path.getmtime(destino) >= os.path.getmtime(origem):
            return destino
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with Image.open(origem) as imagem:
            imagem = ImageOps.exif_transpose(imagem)
            imagem.thumbnail(TAMANHO_MINIATURA)
            if imagem.mode not in ('RGB', 'RGBA'):
                imagem = imagem.convert('RGBA')
            imagem.save(destino, 'WEBP', quality=80, method=4)
        return destino
    except (OSError, ValueError) as erro:
        logging.warning(f"Não foi possível gerar a miniatura de {foto}: {erro}")
        return None


def remover_miniatura(pasta_fotos, foto):
    try:
        os.remove(caminho_miniatura(pasta_fotos, foto))
    except FileNotFoundError:
        pass
    except OSError as erro:
        logging.warning(f"Não foi possível remover a miniatura de {foto}: {erro}")


def gerar_miniaturas_faltantes(pasta_fotos):
    """Gera as miniaturas que ainda não existem. Retorna quantas foram criadas."""
    criadas = 0
    if not os.path.isdir(pasta_fotos):
        return 0
    for nome in sorted(os.listdir(pasta_fotos)):
        if not os.path.isfile(os.path.join(pasta_fotos, nome)):
            continue
        destino = caminho_miniatura(pasta_fotos, nome)
        existia = os.path.exists(destino)
        if gerar_miniatura(pasta_fotos, nome) and not existia:
            criadas += 1
    if criadas:
        logging.info(f"Miniaturas geradas: {criadas}")
    return criadas
