#!/bin/bash

# Script de instalar de AI Bro
# GPL v3, David Baña Szymaniak

YaMostrasteHelp="0"
NoInstalar="0"

MostrarHelp() {
    if [ "$YaMostrasteHelp" == "0" ]; then
        echo "Help"
        echo "---------------------"
        echo ""
        echo "Ejecútalo con sudo"
        YaMostrasteHelp="1"
      fi
}

case "$1" in # aqui se definen los flags
    --help|-h)
        MostrarHelp
        NoInstalar="1"
        ;;
    *)
        ;;
esac


if [ "$EUID" -ne 0 ]; then
    MostrarHelp
    exit 1
fi

if [ "$NoInstalar" == "0" ]; then
    #copiar el script para que sea un comando

    apt install python3 python3-pip python3-venv

    mkdir -p /usr/local/casata/apps/ai-bro/
    cp ai-bro.py /usr/local/casata/apps/ai-bro/ai-bro.py

    cp GUIDE.json /usr/local/casata/apps/ai-bro/GUIDE.json # para poder desinstalarse con Casata

    chmod +x /usr/local/casata/apps/ai-bro/ai-bro.py

    ln -s /usr/local/casata/apps/ai-bro/ai-bro.py /usr/bin/ai-bro

    echo "Creando Python venv en /usr/local/casata/python-venv/"

    python3 -m /usr/local/casata/python-venv/
    source /usr/local/casata/python-venv/
    Dependencias=$(cat full-requirements.txt)
    pip install $Dependencias
    exit

    exit 0 #todo salio bien :)
fi
