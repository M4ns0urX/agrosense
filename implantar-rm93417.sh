#!/bin/bash
# Cria os recursos no Azure, configura e publica a aplicação AgroSense.
# Executar no Azure Cloud Shell (modo Bash), a partir da raiz do repositório:
#   bash implantar-rm93417.sh rm93417
set -euo pipefail

RM="${1:?Uso: bash implantar-rm93417.sh <rm>   ex: bash implantar-rm93417.sh rm93417}"
PROJETO="agrosense"
LOCAL="eastus"
# F0 aceita só um recurso de visão por assinatura. Para o segundo RM na mesma assinatura, use SKU_VISION=S1.
SKU_VISION="${SKU_VISION:-F0}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/app"

RG="rg-${PROJETO}-${RM}"
AIV="aiv-${PROJETO}-${RM}"
PLAN="plan-${PROJETO}-${RM}"
# Nome do Web App precisa ser único no Azure: acrescenta um sufixo aleatório
APP="app-${PROJETO}-${RM}-$(openssl rand -hex 2)"

echo ">> Verificando login no Azure"
az account show --query name -o tsv

echo ">> Resource Group: $RG"
az group create --name "$RG" --location "$LOCAL" --output none

echo ">> Azure AI Vision: $AIV"
az cognitiveservices account create \
  --name "$AIV" --resource-group "$RG" --location "$LOCAL" \
  --kind ComputerVision --sku "$SKU_VISION" --custom-domain "$AIV" --yes --output none

AIV_ENDPOINT="$(az cognitiveservices account show --name "$AIV" --resource-group "$RG" \
  --query properties.endpoint -o tsv)"
AIV_KEY="$(az cognitiveservices account keys list --name "$AIV" --resource-group "$RG" \
  --query key1 -o tsv)"

echo ">> App Service Plan: $PLAN"
az appservice plan create --name "$PLAN" --resource-group "$RG" --location "$LOCAL" \
  --is-linux --sku B1 --output none

echo ">> Web App: $APP"
az webapp create --name "$APP" --resource-group "$RG" --plan "$PLAN" \
  --runtime "PYTHON:3.11" --output none

echo ">> Configurando variáveis e comando de inicialização"
az webapp config appsettings set --name "$APP" --resource-group "$RG" --output none \
  --settings AIV_ENDPOINT="$AIV_ENDPOINT" AIV_KEY="$AIV_KEY" SCM_DO_BUILD_DURING_DEPLOYMENT=true
az webapp config set --name "$APP" --resource-group "$RG" --output none \
  --startup-file "gunicorn --bind=0.0.0.0 --timeout 600 app:app"

echo ">> Publicando a aplicação via Azure CLI"
ZIP_FILE="$(mktemp -d)/app.zip"
(cd "$APP_DIR" && zip -qr "$ZIP_FILE" . -x "__pycache__/*")
az webapp deploy --name "$APP" --resource-group "$RG" \
  --src-path "$ZIP_FILE" --type zip --output none

echo ""
echo "Implantação concluída."
echo "URL: https://${APP}.azurewebsites.net"
echo "Recursos criados no Resource Group $RG:"
az resource list --resource-group "$RG" --query "[].{Nome:name, Tipo:type}" -o table
