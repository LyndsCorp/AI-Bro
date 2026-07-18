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

    apt install python3-pip python3-venv

    mkdir /opt/ai-bro/
    cp ai-bro.py /opt/ai-bro/ai-bro.py

    chmod +x /opt/ai-bro/ai-bro.py

    ln -s /opt/ai-bro/ai-bro.py /usr/bin/ai-bro

    echo "Creando Python venv en /opt/ai-bro/venv"

    python3 -m venv /opt/ai-bro/venv
    source /opt/ai-bro/venv/bin/activate
    Dependencias=$(cat full-requirements.txt)
    pip install $Dependencias
    exit

    exit 0 #todo salio bien :)
fi
