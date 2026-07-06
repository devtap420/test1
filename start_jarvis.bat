@echo off
title Jarvis
cd /d "C:\Users\tapan\Documents\jar"
streamlit run app.py
if errorlevel 1 (
    echo.
    echo Jarvis exited with an error. See the messages above.
    pause
)
