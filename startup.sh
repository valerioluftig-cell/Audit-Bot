#!/bin/bash
# Azure App Service startup script
pip install -r requirements.txt
python -m uvicorn server:app --host 0.0.0.0 --port $PORT
