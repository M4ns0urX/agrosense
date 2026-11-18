import io
import os

import numpy as np
import requests
from flask import Flask, render_template, request
from PIL import Image

app = Flask(__name__)

AIV_ENDPOINT = os.environ.get("AIV_ENDPOINT", "").rstrip("/")
AIV_KEY = os.environ.get("AIV_KEY", "")
MAX_BYTES = 4 * 1024 * 1024  # 4 MB


def carregar_imagem(arquivo):
    """Valida e abre a imagem enviada. Levanta ValueError se for inválida."""
    if arquivo is None or arquivo.filename == "":
        raise ValueError("Nenhuma imagem foi selecionada.")
    dados = arquivo.read()
    if not dados:
        raise ValueError("O arquivo enviado está vazio.")
    if len(dados) > MAX_BYTES:
        raise ValueError("A imagem é maior que 4 MB.")
    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
    except Exception as exc:
        raise ValueError("Arquivo inválido: envie uma imagem JPG ou PNG.") from exc
    return img, dados


def analisar_umidade_solo(img):
    """Estima a umidade do solo pela cor: solo úmido escurece e fica mais saturado."""
    rgb = np.asarray(img.convert("RGB").resize((256, 256)), dtype=float) / 255
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    luminosidade = rgb.mean(axis=2)
    # Pixels de tom terroso: marrom/avermelhado/amarelado (R > G > B)
    terroso = (r > g) & (g > b) & ((r - b) > 0.05)
    base = luminosidade[terroso] if terroso.sum() > 500 else luminosidade.ravel()
    media = float(base.mean())

    # Limiares heurísticos: calibre com fotos reais do seu solo
    if media < 0.35:
        nivel, orientacao = "Alta", "Solo escuro e saturado. Umidade adequada ou alta, evite irrigar."
    elif media < 0.55:
        nivel, orientacao = "Média", "Tom intermediário. Monitore e irrigue se a superfície secar."
    else:
        nivel, orientacao = "Baixa", "Solo claro e pulverulento. Irrigação recomendada."

    return {
        "titulo": "Umidade do solo",
        "resultado": nivel,
        "detalhe": orientacao,
        "metricas": {"Luminosidade média": f"{media:.2f}", "Pixels terrosos": f"{terroso.mean():.0%}"},
    }


def analisar_saude_planta(img):
    """Mede a proporção de pixels verdes para estimar a condição da planta."""
    rgb = np.asarray(img.convert("RGB").resize((256, 256)), dtype=float) / 255
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    verde = (g > r) & (g > b) & (g > 0.2)
    proporcao = float(verde.mean())

    if proporcao >= 0.5:
        nivel, orientacao = "Boa", "Predomínio de verde. Planta aparentemente saudável."
    elif proporcao >= 0.2:
        nivel, orientacao = "Atenção", "Verde reduzido. Verifique rega, nutrientes ou pragas."
    else:
        nivel, orientacao = "Crítica", "Pouca área verde ou solo exposto. Verifique a planta de perto."

    return {
        "titulo": "Condição da planta",
        "resultado": nivel,
        "detalhe": orientacao,
        "metricas": {"Área verde": f"{proporcao:.0%}"},
    }


def consultar_azure_vision(dados):
    """Envia a imagem ao Azure AI Vision e retorna legenda e tags."""
    if not AIV_ENDPOINT or not AIV_KEY:
        raise RuntimeError("Serviço de visão não configurado.")
    resp = requests.post(
        f"{AIV_ENDPOINT}/computervision/imageanalysis:analyze",
        params={"api-version": "2024-02-01", "features": "caption,tags"},
        headers={"Ocp-Apim-Subscription-Key": AIV_KEY, "Content-Type": "application/octet-stream"},
        data=dados,
        timeout=20,
    )
    resp.raise_for_status()
    json_ = resp.json()
    legenda = json_.get("captionResult", {}).get("text", "")
    tags = [t["name"] for t in json_.get("tagsResult", {}).get("values", []) if t.get("confidence", 0) >= 0.6]
    return legenda, tags


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", resultado=None, erro=None)


@app.route("/analisar", methods=["POST"])
def analisar():
    modo = request.form.get("modo", "solo")
    try:
        img, dados = carregar_imagem(request.files.get("imagem"))
    except ValueError as exc:
        return render_template("index.html", resultado=None, erro=str(exc)), 400

    analise = analisar_umidade_solo(img) if modo == "solo" else analisar_saude_planta(img)

    try:
        legenda, tags = consultar_azure_vision(dados)
        analise["legenda"] = legenda
        analise["tags"] = tags
    except requests.RequestException:
        analise["aviso"] = "Não foi possível consultar o Azure AI Vision agora. Tente novamente mais tarde."
    except RuntimeError as exc:
        analise["aviso"] = str(exc)

    return render_template("index.html", resultado=analise, erro=None)


if __name__ == "__main__":
    app.run(debug=True)

